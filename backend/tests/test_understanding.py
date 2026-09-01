"""Intent understanding and catalog grounding.

The behaviour under test is the one the agent got wrong: asked to make pasta,
it proposed ₹2,499 headphones. Not because it misread the sentence, but
because selection fell back to "rank the whole catalog" whenever nothing
matched, and the highest-rated product always won.

So most of these tests are about refusing. An agent that says "we do not
stock that" is correct; one that confidently substitutes something unrelated
is worse than one that says nothing at all.
"""

import pytest

from app.agent import find_relevant
from app.agent.matching import query_terms, unmatched_items
from app.agent.understanding import _from_gemini, _from_rules
from app.models import Product
from app.services import gemini
from app.utils.money import rupees_to_paise
from tests.conftest import requires_db


def product(name, rupees, *, category="groceries", rating=4.0, description=""):
    return Product(
        id=f"prd_{name.lower().replace(' ', '_')}",
        name=name,
        description=description,
        price_paise=rupees_to_paise(rupees),
        currency="INR",
        category=category,
        merchant="Blinkit",
        rating=rating,
        attributes={},
        in_stock=True,
    )


SHELF = [
    product("Amul Gold Milk 1L", 68, rating=4.5, description="Full cream milk."),
    product("Britannia Brown Bread", 45, rating=4.1, description="Whole wheat loaf."),
    product("Farm Eggs (12)", 89, rating=4.3, description="Free-range eggs."),
    product("Weekly Veggie Box", 420, rating=4.4, description="Seasonal vegetables."),
    product("India Gate Basmati 5kg", 649, rating=4.6, description="Aged basmati rice."),
    product("Premium Audio Max", 2499, category="electronics", rating=4.8,
            description="Flagship over-ear headphones, 60h playback."),
]


# --- Grounding an intent in the catalog ----------------------------------


def test_named_items_we_do_not_stock_return_nothing():
    """The bug, stated as a test.

    Pasta is not in the catalog. The correct answer is an empty list, not the
    best-rated thing on the shelf.
    """
    matches = find_relevant(SHELF, items=["pasta", "tomato"], category="groceries")

    assert matches == []


def test_a_failed_item_search_does_not_widen_to_the_category():
    """Widening to 'groceries' is a smaller version of the same guess."""
    matches = find_relevant(SHELF, items=["pasta"], category="groceries")

    assert not any(m.product.category == "groceries" for m in matches)


def test_headphones_are_never_proposed_for_a_cooking_request():
    matches = find_relevant(
        SHELF, items=["pasta", "tomato", "cheese"], query="i want to make pasta"
    )

    assert "Premium Audio Max" not in [m.product.name for m in matches]


def test_matching_items_are_found():
    matches = find_relevant(SHELF, items=["milk", "bread"])
    names = [m.product.name for m in matches]

    assert "Amul Gold Milk 1L" in names
    assert "Britannia Brown Bread" in names
    assert "Premium Audio Max" not in names


def test_items_are_matched_on_word_boundaries_not_substrings():
    """'egg' must not match 'Weekly Veggie Box'.

    Substring matching did exactly that, and someone asking for eggs was
    handed a vegetable box with nothing to indicate a mistake.
    """
    names = [m.product.name for m in find_relevant(SHELF, items=["egg"])]

    assert names == ["Farm Eggs (12)"]


def test_synonyms_reach_the_shelf_label():
    """A shopper says 'rice'; the label says 'India Gate Basmati'."""
    names = [m.product.name for m in find_relevant(SHELF, items=["rice"])]

    assert names == ["India Gate Basmati 5kg"]


def test_products_answering_more_of_the_request_rank_first():
    shelf = [
        product("Milk and Bread Combo", 100, description="milk and bread together"),
        product("Amul Gold Milk 1L", 68, description="Full cream milk."),
    ]
    matches = find_relevant(shelf, items=["milk", "bread"])

    assert matches[0].product.name == "Milk and Bread Combo"


def test_a_bare_category_still_narrows_when_nothing_was_named():
    """'Buy some groceries' is a real request; it just is not a specific one."""
    matches = find_relevant(SHELF, items=[], query="groceries", category="groceries")

    assert matches
    assert all(m.product.category == "groceries" for m in matches)


def test_query_terms_drop_filler():
    assert "want" not in query_terms("I want to make pasta")
    assert "pasta" in query_terms("I want to make pasta")


def test_unmatched_items_are_reported():
    matches = find_relevant(SHELF, items=["rice", "chicken", "saffron"])

    assert unmatched_items(["rice", "chicken", "saffron"], matches) == [
        "chicken",
        "saffron",
    ]


# --- Reading the request -------------------------------------------------


def test_rules_parser_expands_a_known_dish():
    intent = _from_rules("I want to make pasta")

    assert intent.dish == "pasta"
    assert intent.kind == "cook"
    assert "pasta" in intent.required_items


def test_rules_parser_leaves_product_requests_itemless():
    """'best' and 'wireless' describe a product; they are not things a shop
    can fail to stock, so they must never be reported as unavailable."""
    intent = _from_rules("Buy me the best headphones you can find")

    assert intent.required_items == []
    assert intent.category == "electronics"


def test_an_empty_request_asks_rather_than_guesses():
    intent = _from_rules("buy")

    assert intent.needs_clarification
    assert intent.clarification


# --- Gemini, and distrusting what it returns -----------------------------


def test_gemini_output_is_validated_not_trusted():
    """A category that does not exist, a negative budget and an invented
    preference all have to be dropped here rather than confuse scoring."""
    intent = _from_gemini(
        "buy me headphones",
        {
            "intent": "buy",
            "dish": "",
            "required_items": ["headphones"],
            "category": "spacecraft",
            "constraints": [],
            "max_budget_rupees": -5,
            "preferences": ["vibes", "rating"],
            "ambiguous": False,
            "clarification": "",
        },
        categories=["electronics", "groceries"],
    )

    assert intent.category == "electronics"  # fell back to the rules reading
    assert intent.max_budget_paise is None
    assert "vibes" not in intent.preferences
    assert "rating" in intent.preferences


def test_a_stated_budget_beats_the_models_opinion_of_it():
    """The regex cannot hallucinate a number that was never written down."""
    intent = _from_gemini(
        "headphones under 2000",
        {
            "intent": "buy",
            "dish": "",
            "required_items": ["headphones"],
            "category": "electronics",
            "constraints": [],
            "max_budget_rupees": 99999,
            "preferences": [],
            "ambiguous": False,
            "clarification": "",
        },
        categories=["electronics"],
    )

    assert intent.max_budget_paise == rupees_to_paise(2000)


def test_ambiguity_is_ignored_when_items_were_still_identified():
    intent = _from_gemini(
        "something for breakfast",
        {
            "intent": "buy",
            "dish": "breakfast",
            "required_items": ["milk", "bread"],
            "category": "groceries",
            "constraints": [],
            "max_budget_rupees": 0,
            "preferences": [],
            "ambiguous": True,
            "clarification": "What kind of breakfast?",
        },
        categories=["groceries"],
    )

    assert not intent.needs_clarification


def test_gemini_is_skipped_when_unconfigured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")

    assert gemini.understand_goal("anything", categories=[]) is None


def test_a_gemini_failure_never_raises(monkeypatch):
    """The console must keep working when the quota is spent or the network
    is down. A degraded parse is a worse answer; a 500 is a broken product."""
    import httpx

    from app.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def explode(*args, **kwargs):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "post", explode)

    assert gemini.understand_goal("buy milk", categories=["groceries"]) is None


def test_non_json_from_gemini_is_rejected(monkeypatch):
    import httpx

    from app.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    class Fake:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": "sorry, I can't do that"}]}}
                ]
            }

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Fake())

    assert gemini.understand_goal("buy milk", categories=["groceries"]) is None


# --- End to end, against a real catalog ----------------------------------


@requires_db
def test_a_cooking_request_we_cannot_fill_proposes_nothing(db, world):
    """The original bug, end to end: the demo catalog has no pasta, so the
    agent must decline instead of proposing headphones."""
    from app.agent import recommend

    result = recommend(db, "I want to make pasta")

    assert result.chosen is None
    assert result.status == "no_match"
    assert "pasta" in result.unavailable


@requires_db
def test_the_headphone_demo_still_works(db, world):
    """The path the whole demo rests on must be untouched by any of this."""
    from app.agent import recommend

    result = recommend(db, "Buy me wireless headphones under 2000 with good battery life")

    assert result.status == "ok"
    assert result.chosen.product.name == "SoundBeat Pro"


@requires_db
def test_the_agent_may_still_propose_something_the_policy_refuses(db, world):
    from app.agent import recommend

    result = recommend(db, "Buy me the best headphones you can find")

    assert result.chosen.product.name == "Premium Audio Max"


@requires_db
def test_no_model_is_needed_for_any_of_this(db, world, monkeypatch):
    """Every assertion above holds with Gemini switched off. The model
    improves the reading; it is never load-bearing."""
    from app.config import settings

    from app.agent import recommend

    monkeypatch.setattr(settings, "gemini_api_key", "")

    assert recommend(db, "I want to make pasta").chosen is None
    assert recommend(db, "headphones under 2000").chosen is not None
