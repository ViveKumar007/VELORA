"""Agent tests.

The agent is allowed to be wrong about what it can afford. What it must not
be is unpredictable, so these tests pin the parsing and ranking behaviour the
demo depends on.
"""

import pytest

from app.agent import extract_intent, rank, score_product
from app.models import Product
from app.utils.money import rupees_to_paise


def product(name, rupees, *, category="electronics", rating=4.0, battery=None, **attrs):
    attributes = dict(attrs)
    if battery is not None:
        attributes["battery_hours"] = battery
    return Product(
        id=f"prd_{name.lower().replace(' ', '_')}",
        name=name,
        description="",
        price_paise=rupees_to_paise(rupees),
        currency="INR",
        category=category,
        merchant="DemoStore",
        rating=rating,
        attributes=attributes,
        in_stock=True,
    )


CATALOG = [
    product("SoundBeat Lite", 1299, rating=4.2, battery=30),
    product("SoundBeat Pro", 1799, rating=4.6, battery=50),
    product("Premium Audio Max", 2499, rating=4.8, battery=60),
    product("Gaming Subscription", 999, category="digital_goods", rating=4.1),
]


# --- Intent extraction ---------------------------------------------------


def test_extracts_budget_category_and_preferences():
    intent = extract_intent("Buy me wireless headphones under 2,000 with good battery life.")

    assert intent.max_budget_paise == rupees_to_paise(2000)
    assert intent.category == "electronics"
    assert "battery_life" in intent.preferences
    assert "headphones" in intent.product_query


@pytest.mark.parametrize(
    "text,expected_rupees",
    [
        ("headphones under 2000", 2000),
        ("headphones under ₹2,000", 2000),
        ("headphones below Rs. 1500", 1500),
        ("earbuds within 2k", 2000),
        ("speaker up to INR 3,499.50", 3499.50),
        ("laptop no more than 50,000", 50000),
    ],
)
def test_budget_parsing_handles_common_phrasings(text, expected_rupees):
    assert extract_intent(text).max_budget_paise == rupees_to_paise(expected_rupees)


def test_missing_budget_is_none_not_zero():
    """None means unspecified. Zero would mean 'can afford nothing'."""
    assert extract_intent("buy me headphones").max_budget_paise is None


def test_category_detection():
    assert extract_intent("get a gaming subscription").category == "digital_goods"
    assert extract_intent("book a flight to Delhi").category == "travel"
    assert extract_intent("something entirely unrelated").category is None


# --- Scoring -------------------------------------------------------------


def test_battery_preference_beats_a_cheaper_option():
    intent = extract_intent("headphones under 2000 with long battery life")
    ranked = rank(CATALOG, intent)

    assert ranked[0].product.name == "SoundBeat Pro"


def test_price_preference_prefers_the_cheaper_option():
    intent = extract_intent("cheapest headphones under 2000")
    ranked = rank(CATALOG, intent)

    assert ranked[0].product.name == "SoundBeat Lite"


def test_over_budget_items_rank_below_affordable_ones():
    intent = extract_intent("headphones under 2000 with long battery life")
    ranked = rank(CATALOG, intent)

    affordable = [s for s in ranked if s.within_budget]
    over = [s for s in ranked if not s.within_budget]
    assert ranked[: len(affordable)] == affordable
    assert any(s.product.name == "Premium Audio Max" for s in over)


def test_agent_may_propose_something_the_policy_will_refuse():
    """With no budget stated, the agent picks the best product on merit --
    which is exactly the case the gate exists to catch."""
    intent = extract_intent("buy me the best headphones you can find")
    ranked = rank(CATALOG, intent)

    assert ranked[0].product.name == "Premium Audio Max"


def test_scores_are_explainable():
    intent = extract_intent("headphones under 2000 with good battery life")
    scored = score_product(CATALOG[1], intent, best_battery=60)

    assert set(scored.breakdown) == {
        "budget", "rating", "battery_life", "preference", "category",
    }
    assert 0 <= scored.score <= 1
    assert scored.notes


def test_out_of_stock_items_are_never_recommended():
    catalog = [product("Sold Out Pro", 1000, rating=5.0)]
    catalog[0].in_stock = False

    assert rank(catalog, extract_intent("headphones under 2000")) == []


def test_ranking_is_deterministic():
    intent = extract_intent("headphones under 2000 with good battery life")
    first = [s.product.name for s in rank(CATALOG, intent)]
    second = [s.product.name for s in rank(CATALOG, intent)]

    assert first == second
