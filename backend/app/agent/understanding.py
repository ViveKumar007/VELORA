"""Understanding a request, kept separate from acting on one.

Two stages, and the separation is the point:

    understand()  what does this person need?      (Gemini, or rules)
    matching      what does the catalog have?      (deterministic)
    scoring       which of those is best?          (deterministic)
    the gate      may they buy it?                 (deterministic, no model)

Only the first stage is allowed to be clever, and it never sees a price, a
policy or a product. It reads English and returns nouns. Everything that
follows is ordinary code, so a model that misreads a request can produce an
unhelpful recommendation but can never produce an unauthorised purchase.

When Gemini is unconfigured or unreachable, the rules parser in intent.py
answers instead and the product keeps working -- with a narrower
understanding of English, not a broken agent.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.intent import ShoppingIntent, extract_intent
from app.models import Product
from app.services import gemini
from app.utils.money import rupees_to_paise

#: Preference names scoring.py knows how to weigh. Anything else Gemini
#: proposes is dropped rather than silently ignored downstream.
KNOWN_PREFERENCES = frozenset(
    {"price", "rating", "battery_life", "noise_cancellation"}
)

#: Dish knowledge for when Gemini is not available. Small on purpose: this is
#: a fallback that keeps the demo honest offline, not an attempt to
#: reimplement a language model in a dictionary.
DISH_ITEMS: dict[str, tuple[str, ...]] = {
    "pasta": ("pasta", "tomato", "olive oil", "cheese"),
    "biryani": ("rice", "chicken", "spices", "onion", "yoghurt"),
    "omelette": ("egg", "onion", "butter"),
    "omelet": ("egg", "onion", "butter"),
    "sandwich": ("bread", "butter", "cheese"),
    "toast": ("bread", "butter"),
    "pancake": ("egg", "milk", "flour"),
    "curry": ("onion", "tomato", "spices", "oil"),
    "salad": ("vegetable", "olive oil"),
    "breakfast": ("milk", "bread", "egg"),
    "cereal": ("milk", "cereal"),
    "coffee": ("coffee", "milk"),
    "tea": ("tea", "milk"),
}

_COOKING_WORDS = ("cook", "make", "prepare", "recipe", "ingredient", "dish")


def catalog_vocabulary(db: Session) -> tuple[list[str], str]:
    """What this shop actually sells, for grounding the reading.

    Passed to Gemini so it can pick a sensible category, never so it can pick
    a product -- product choice belongs to the deterministic layer.
    """
    categories = sorted(
        {c for c in db.scalars(select(Product.category).distinct()) if c}
    )
    names = list(db.scalars(select(Product.name).limit(40)))
    return categories, ", ".join(names)


def _clean_items(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip().lower()
        if text and text not in seen:
            seen.append(text)
    return seen[:12]


def _from_gemini(goal: str, data: dict, categories: list[str]) -> ShoppingIntent:
    """Turn Gemini's JSON into an intent, distrusting every field.

    The schema constrains the shape, not the sense: a category that does not
    exist, a budget of -5, or a preference scoring.py has never heard of all
    have to be rejected here rather than confusing something downstream.
    """
    rules = extract_intent(goal)

    category = (data.get("category") or "").strip().lower() or None
    if category not in categories:
        category = None

    budget_rupees = data.get("max_budget_rupees") or 0
    try:
        budget = rupees_to_paise(float(budget_rupees)) if float(budget_rupees) > 0 else None
    except (TypeError, ValueError):
        budget = None
    # The regex is better at "under ₹2,000" than a model is, and it cannot
    # hallucinate a number that was never written down.
    budget = rules.max_budget_paise or budget

    preferences = [
        p.strip().lower()
        for p in (data.get("preferences") or [])
        if isinstance(p, str) and p.strip().lower() in KNOWN_PREFERENCES
    ]
    for preference in rules.preferences:
        if preference not in preferences:
            preferences.append(preference)

    dish = (data.get("dish") or "").strip() or None
    items = _clean_items(data.get("required_items"))
    ambiguous = bool(data.get("ambiguous")) and not items
    clarification = (data.get("clarification") or "").strip() or None

    kind = (data.get("intent") or "buy").strip().lower()
    if kind not in {"buy", "cook", "restock", "unknown"}:
        kind = "buy"

    return ShoppingIntent(
        raw_text=goal,
        product_query=rules.product_query,
        max_budget_paise=budget,
        category=category or rules.category,
        preferences=preferences,
        kind=kind,
        dish=dish,
        required_items=items,
        constraints=[
            c.strip() for c in (data.get("constraints") or []) if isinstance(c, str) and c.strip()
        ][:8],
        needs_clarification=ambiguous,
        clarification=clarification if ambiguous else None,
        source="gemini",
    )


def _from_rules(goal: str) -> ShoppingIntent:
    """The offline reading: the original parser, plus a dish lookup.

    It recognises far less English than Gemini does, but it never invents and
    it never fails, which is what a fallback is for.
    """
    intent = extract_intent(goal)
    lowered = goal.lower()

    from app.agent.matching import query_terms

    dish = next((name for name in DISH_ITEMS if name in lowered), None)
    if dish:
        intent.required_items = list(DISH_ITEMS[dish])
        intent.kind = "cook" if any(w in lowered for w in _COOKING_WORDS) else "buy"
        intent.dish = dish
        # A dish is groceries unless the request already said otherwise.
        intent.category = intent.category or "groceries"
    else:
        # No dish named, so the request is about a product rather than a
        # recipe. required_items stays empty and matching works from the
        # query: "best" and "wireless" are how someone describes a thing,
        # not things a shop can fail to stock, and reporting them as
        # unavailable would be nonsense.
        intent.required_items = []

    intent.source = "rules"

    if not intent.required_items and not query_terms(intent.product_query or goal):
        intent.needs_clarification = True
        intent.clarification = (
            "What would you like to buy? Naming an item or a dish is enough."
        )
    return intent


def understand(db: Session, goal: str) -> ShoppingIntent:
    """Read a request into a structured intent.

    Gemini first when it is configured, the rules parser otherwise or on any
    failure. The caller cannot tell which answered except by reading
    `intent.source`, and nothing downstream behaves differently.
    """
    categories, vocabulary = catalog_vocabulary(db)

    data = gemini.understand_goal(goal, categories=categories, vocabulary=vocabulary)
    if data is not None:
        return _from_gemini(goal, data, categories)

    return _from_rules(goal)
