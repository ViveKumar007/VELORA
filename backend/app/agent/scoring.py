"""Product scoring.

Every score is a weighted sum of components that are each reported alongside
the total, so the agent console can show *why* an item won rather than
asserting that it did. An opaque recommendation is not much better than a
guess.

Scoring never considers policy limits. The agent is allowed to want something
it cannot have -- discovering that is the gate's job, and keeping the two
separate is what the demo is built to show.
"""

from dataclasses import dataclass, field

from app.agent.intent import ShoppingIntent
from app.gate import normalize_category
from app.models import Product
from app.utils.money import format_inr

#: Always applied -- every shopper cares about cost, quality and relevance.
BASE_WEIGHTS = {
    "budget": 0.35,
    "rating": 0.30,
    "category": 0.15,
}

#: Applied only when the request actually asks for them. A shopper who said
#: "cheapest" should not lose to a pricier model on a battery spec they never
#: mentioned, so unrequested dimensions carry no weight at all.
OPTIONAL_WEIGHTS = {
    "battery_life": 0.35,
    "preference": 0.20,
}


def active_weights(intent: ShoppingIntent, has_other_preferences: bool) -> dict[str, float]:
    """Select the live components and renormalise them to sum to 1, so totals
    stay comparable no matter how much the request specified."""
    weights = dict(BASE_WEIGHTS)
    if "battery_life" in intent.preferences:
        weights["battery_life"] = OPTIONAL_WEIGHTS["battery_life"]
    if has_other_preferences:
        weights["preference"] = OPTIONAL_WEIGHTS["preference"]

    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


@dataclass
class ScoredProduct:
    product: Product
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    within_budget: bool = True

    def to_dict(self) -> dict:
        return {
            "product_id": self.product.id,
            "name": self.product.name,
            "price_paise": self.product.price_paise,
            "price_display": format_inr(self.product.price_paise),
            "category": self.product.category,
            "merchant": self.product.merchant,
            "rating": self.product.rating,
            "attributes": self.product.attributes or {},
            "score": round(self.score, 4),
            "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()},
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "notes": list(self.notes),
            "within_budget": self.within_budget,
        }


def _budget_component(product: Product, intent: ShoppingIntent) -> tuple[float, str | None]:
    if intent.max_budget_paise is None:
        return 0.6, None
    if product.price_paise > intent.max_budget_paise:
        return 0.0, f"{format_inr(product.price_paise)} is over the stated budget"

    headroom = 1 - (product.price_paise / intent.max_budget_paise)
    if "price" in intent.preferences:
        # Cheapness was asked for: reward unspent budget.
        return 0.5 + 0.5 * headroom, "cheaper option within budget"
    # Otherwise a comfortable fit scores well without punishing quality.
    return 0.75 + 0.25 * headroom, None


def _battery_component(
    product: Product, intent: ShoppingIntent, best_battery: float
) -> tuple[float, str | None]:
    hours = float((product.attributes or {}).get("battery_hours") or 0)
    if not hours or not best_battery:
        return 0.0, None
    ratio = hours / best_battery
    note = f"{hours:g}h battery" + (" (best available)" if ratio >= 1 else "")
    return ratio, note if "battery_life" in intent.preferences else None


def score_product(
    product: Product, intent: ShoppingIntent, *, best_battery: float = 0.0
) -> ScoredProduct:
    breakdown: dict[str, float] = {}
    notes: list[str] = []

    budget_score, budget_note = _budget_component(product, intent)
    breakdown["budget"] = budget_score
    if budget_note:
        notes.append(budget_note)

    breakdown["rating"] = min(1.0, (product.rating or 0) / 5.0)
    if (product.rating or 0) >= 4.5:
        notes.append(f"rated {product.rating}")

    battery_score, battery_note = _battery_component(product, intent, best_battery)
    breakdown["battery_life"] = battery_score
    if battery_note:
        notes.append(battery_note)

    attributes = product.attributes or {}
    matched = [
        preference
        for preference in intent.preferences
        if preference not in ("price", "rating", "battery_life")
        and bool(attributes.get(preference))
    ]
    breakdown["preference"] = 1.0 if matched else 0.0
    notes.extend(m.replace("_", " ") for m in matched)

    category_match = (
        intent.category is not None
        and normalize_category(product.category) == normalize_category(intent.category)
    )
    breakdown["category"] = 1.0 if category_match else (0.5 if intent.category is None else 0.0)

    requested_other = [
        p for p in intent.preferences if p not in ("price", "rating", "battery_life")
    ]
    weights = active_weights(intent, has_other_preferences=bool(requested_other))

    # Components outside the active set are reported but not scored, so the
    # UI can still show the full picture of what was considered.
    total = sum(weight * breakdown.get(key, 0.0) for key, weight in weights.items())
    within_budget = (
        intent.max_budget_paise is None or product.price_paise <= intent.max_budget_paise
    )

    return ScoredProduct(
        product=product,
        score=total,
        breakdown=breakdown,
        weights=weights,
        notes=notes,
        within_budget=within_budget,
    )


def rank(products: list[Product], intent: ShoppingIntent) -> list[ScoredProduct]:
    """Score and sort a catalog against an intent, best first."""
    in_stock = [p for p in products if p.in_stock]
    best_battery = max(
        (float((p.attributes or {}).get("battery_hours") or 0) for p in in_stock),
        default=0.0,
    )
    scored = [score_product(p, intent, best_battery=best_battery) for p in in_stock]
    return sorted(scored, key=lambda s: (s.within_budget, s.score), reverse=True)
