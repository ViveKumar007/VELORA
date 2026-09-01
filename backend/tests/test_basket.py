"""Multi-item baskets.

A basket is one authorization decision about several products. That makes two
things worth pinning hard: the amount judged is the *sum* read from the
catalog, and the scope checks are unanimous rather than lenient — a basket is
inside the boundary only if every line in it is.

The rest of these tests exist because a basket is the first thing in Velora
that is not one product, and every invariant that held for one product has to
still hold for five.
"""

import uuid

import pytest

from app.agent.basket import recommend_basket
from app.agent.matching import find_relevant
from app.gate import EvalContext, evaluate
from app.gate.checks import check_category, check_merchant
from app.models import Decision, Product, TxnState
from app.services.gateway import handle_basket_request
from app.utils.money import rupees_to_paise
from tests.conftest import requires_db


def product(name, rupees, *, category="groceries", merchant="Blinkit", rating=4.0, description=""):
    return Product(
        id=f"prd_{name.lower().replace(' ', '_')}",
        name=name,
        description=description,
        price_paise=rupees_to_paise(rupees),
        currency="INR",
        category=category,
        merchant=merchant,
        rating=rating,
        attributes={},
        in_stock=True,
    )


# --- Relevance, which the basket depends on entirely -------------------


def test_a_negated_ingredient_is_not_a_match():
    """The bug that made baskets unusable.

    A synced product called "Tomato Ketchup No Onion No Garlic" was being
    returned as the best match for "onion" -- a sauce whose name says, in
    words, that it contains none.
    """
    shelf = [
        product("Surabhi Tomato Ketchup No Onion No Garlic", 87),
        product("Unbranded Onion", 54),
    ]
    names = [m.product.name for m in find_relevant(shelf, items=["onion"])]

    assert names == ["Unbranded Onion"]


def test_a_name_match_outranks_a_description_match():
    """The sync tags every row with the term it was found under, so
    descriptions are partly machine-written and must count for less than the
    product's own title."""
    shelf = [
        product("Maggi Rich Tomato Ketchup", 15, description="groceries · tomato"),
        product("Desi Tomato", 18, description="groceries"),
    ]
    matches = find_relevant(shelf, items=["tomato"])

    assert matches[0].product.name == "Desi Tomato"


def test_negation_only_applies_to_the_negated_mention():
    shelf = [product("Onion Rings with No Garlic", 40)]

    assert [m.product.name for m in find_relevant(shelf, items=["onion"])] == [
        "Onion Rings with No Garlic"
    ]
    assert find_relevant(shelf, items=["garlic"]) == []


# --- Scope checks are unanimous ----------------------------------------


class _Policy:
    def __init__(self, merchants=None, categories=None):
        self.allowed_merchants = merchants or []
        self.allowed_categories = categories or []


def _ctx(merchants, categories, policy):
    return EvalContext(
        agent=None,
        now=None,
        policy=policy,
        merchants=merchants,
        categories=categories,
        merchant=merchants[0] if merchants else "",
        category=categories[0] if categories else "",
    )


def test_a_basket_spanning_two_allowed_merchants_passes():
    result = check_merchant(_ctx(["Blinkit", "Zepto"], ["groceries"],
                                _Policy(merchants=["Blinkit", "Zepto"])))

    assert result.status == "PASS"
    assert "All 2 merchants" in result.detail


def test_one_disallowed_merchant_refuses_the_whole_basket():
    """Unanimity, not majority. Approving a basket approves every line in it,
    so a single Amazon line makes the basket unauthorized."""
    result = check_merchant(_ctx(["Blinkit", "Zepto", "Amazon"], ["groceries"],
                                 _Policy(merchants=["Blinkit", "Zepto"])))

    assert result.status == "FAIL"
    assert result.reason_code == "MERCHANT_NOT_ALLOWED"
    # Naming the offender, not the set -- "one of your items" is not actionable.
    assert "Amazon" in result.detail


def test_one_disallowed_category_refuses_the_whole_basket():
    result = check_category(_ctx(["Blinkit"], ["groceries", "electronics"],
                                 _Policy(categories=["groceries"])))

    assert result.status == "FAIL"
    assert "electronics" in result.detail


def test_single_item_scope_checks_are_unchanged():
    """A basket-shaped context must not alter the single-purchase path."""
    single = EvalContext(agent=None, now=None, policy=_Policy(merchants=["Blinkit"]),
                         merchant="Blinkit")

    assert single.is_basket is False
    assert check_merchant(single).status == "PASS"
    assert check_merchant(
        EvalContext(agent=None, now=None, policy=_Policy(merchants=["Blinkit"]),
                    merchant="Amazon")
    ).status == "FAIL"


# --- Assembling the list -----------------------------------------------


@requires_db
def test_a_basket_has_one_line_per_ingredient(db, world):
    """Each ingredient is searched on its own, so rice competes with rice."""
    db.add(product("Amul Gold Milk 1L", 68, description="Full cream milk."))
    db.add(product("Britannia Brown Bread", 45, description="Whole wheat loaf."))
    db.commit()

    basket = recommend_basket(db, "i need milk and bread")
    items = {line.item for line in basket.lines}

    assert basket.status == "ok"
    assert {"milk", "bread"} <= items
    assert basket.total_paise == sum(line.product.price_paise for line in basket.lines)


@requires_db
def test_one_product_cannot_fill_two_ingredients(db, world):
    """Otherwise 'tomato' and 'tomato sauce' both resolve to the same bottle
    and the buyer is charged for it twice."""
    db.add(product("Kissan Tomato Ketchup", 99, description="tomato sauce"))
    db.commit()

    basket = recommend_basket(db, "i need tomato and tomato sauce")
    chosen = [line.product.id for line in basket.lines]

    assert len(chosen) == len(set(chosen))


@requires_db
def test_ingredients_the_catalog_cannot_fill_are_reported(db, world):
    basket = recommend_basket(db, "i want to make pasta")

    assert basket.unavailable or basket.status == "no_match"


# --- The gate, on a basket ---------------------------------------------


@requires_db
def test_the_basket_total_is_what_the_limit_judges(db, world):
    """Three items under the limit individually, over it together."""
    ids = []
    for name, price in [("Item A", 800), ("Item B", 800), ("Item C", 800)]:
        p = product(name, price, category="electronics", merchant="DemoStore")
        db.add(p)
        ids.append(p.id)
    db.commit()

    txn, _ = handle_basket_request(
        db, world["agent"], product_ids=ids,
        idempotency_key=f"bsk_{uuid.uuid4().hex[:12]}", label="Three items",
    )

    # Policy allows 2,000 per purchase; 3 x 800 = 2,400.
    assert txn.requested_amount_paise == rupees_to_paise(2400)
    assert txn.decision == Decision.BLOCKED
    assert txn.reason_code == "MAX_AMOUNT_EXCEEDED"
    assert txn.state == TxnState.BLOCKED


@requires_db
def test_a_blocked_basket_reserves_no_budget(db, world):
    before = world["policy"].amount_reserved_paise
    p = product("Far Too Expensive", 9999, category="electronics", merchant="DemoStore")
    db.add(p)
    db.commit()

    txn, _ = handle_basket_request(
        db, world["agent"], product_ids=[p.id],
        idempotency_key=f"bsk_{uuid.uuid4().hex[:12]}",
    )
    db.refresh(world["policy"])

    assert txn.decision == Decision.BLOCKED
    assert world["policy"].amount_reserved_paise == before


@requires_db
def test_prices_come_from_the_catalog_not_the_caller(db, world):
    """The caller sends ids and nothing else. There is no field in which a
    basket could understate what it is worth."""
    p = product("Priced Item", 1200, category="electronics", merchant="DemoStore")
    db.add(p)
    db.commit()

    txn, _ = handle_basket_request(
        db, world["agent"], product_ids=[p.id],
        idempotency_key=f"bsk_{uuid.uuid4().hex[:12]}",
    )

    assert txn.requested_amount_paise == rupees_to_paise(1200)
    assert txn.basket["total_paise"] == rupees_to_paise(1200)


@requires_db
def test_a_basket_is_idempotent_like_any_other_request(db, world):
    p = product("Repeat Item", 500, category="electronics", merchant="DemoStore")
    db.add(p)
    db.commit()
    key = f"bsk_{uuid.uuid4().hex[:12]}"

    first, replayed_first = handle_basket_request(
        db, world["agent"], product_ids=[p.id], idempotency_key=key)
    second, replayed_second = handle_basket_request(
        db, world["agent"], product_ids=[p.id], idempotency_key=key)

    assert replayed_first is False
    assert replayed_second is True
    assert first.id == second.id


@requires_db
def test_the_basket_contents_are_snapshotted(db, world):
    """Like policy_snapshot, and for the same reason: the record must stay
    true to the moment the decision was made, even if a price changes."""
    p = product("Snapshot Item", 300, category="electronics", merchant="DemoStore")
    db.add(p)
    db.commit()

    txn, _ = handle_basket_request(
        db, world["agent"], product_ids=[p.id],
        idempotency_key=f"bsk_{uuid.uuid4().hex[:12]}")

    p.price_paise = rupees_to_paise(9999)
    db.commit()

    assert txn.basket["items"][0]["price_paise"] == rupees_to_paise(300)
    assert txn.requested_amount_paise == rupees_to_paise(300)


@requires_db
def test_an_empty_basket_is_refused(db, world):
    with pytest.raises(ValueError):
        handle_basket_request(db, world["agent"], product_ids=[],
                              idempotency_key=f"bsk_{uuid.uuid4().hex[:12]}")


@requires_db
def test_a_basket_still_cannot_reach_payment_when_blocked(db, world):
    """The invariant the whole product rests on, restated for baskets."""
    from app.services.payments_flow import PaymentNotAllowed, create_payment

    p = product("Blocked Basket Item", 9999, category="electronics", merchant="DemoStore")
    db.add(p)
    db.commit()

    txn, _ = handle_basket_request(
        db, world["agent"], product_ids=[p.id],
        idempotency_key=f"bsk_{uuid.uuid4().hex[:12]}")
    assert txn.decision == Decision.BLOCKED

    with pytest.raises(PaymentNotAllowed):
        create_payment(db, txn.id)
