"""Recovered sales.

A guardrail that only says no costs the merchant every sale it blocks. These
pin the behaviour that turns a refusal into an offer the buyer may accept --
and, just as importantly, the cases where offering one would be wrong.
"""

import pytest

from app.agent.recovery import RECOVERABLE, find_recovery
from app.gate import EvalContext, ReasonCode, evaluate
from app.models import Decision, utcnow
from tests.conftest import requires_db

pytestmark = requires_db


def context_for(world, product):
    return EvalContext(
        agent=world["agent"],
        now=utcnow(),
        policy=world["policy"],
        product=product,
        amount_paise=product.price_paise,
        currency=product.currency,
        category=product.category,
        merchant=product.merchant,
    )


def test_price_block_offers_a_cheaper_in_policy_alternative(db, world):
    """The headline: 2,499 refused against a 2,000 limit returns the 1,799."""
    premium = world["products"]["premium"]
    ctx = context_for(world, premium)
    verdict = evaluate(ctx)
    assert verdict.reason_code == ReasonCode.MAX_AMOUNT_EXCEEDED

    recovery = find_recovery(db, ctx, verdict.reason_code)

    assert recovery is not None, "a recoverable block must produce an offer"
    assert recovery.product.name == "SoundBeat Pro"
    assert recovery.product.price_paise < premium.price_paise


def test_the_offer_is_the_closest_fit_not_the_cheapest(db, world):
    """A buyer refused a 2,499 item wants the 1,799, not the 1,299.

    Offering the cheapest thing available would leave money on the table for
    the merchant and under-serve the buyer.
    """
    ctx = context_for(world, world["products"]["premium"])
    recovery = find_recovery(db, ctx, ReasonCode.MAX_AMOUNT_EXCEEDED)

    assert recovery.product.name == "SoundBeat Pro"          # 1,799
    assert recovery.product.name != "SoundBeat Lite"         # 1,299


def test_every_offer_would_itself_pass_the_gate(db, world):
    """The property that makes offers trustworthy.

    Suggesting something that would also be refused is worse than suggesting
    nothing: it teaches the buyer that refusals are noise.
    """
    ctx = context_for(world, world["products"]["premium"])
    recovery = find_recovery(db, ctx, ReasonCode.MAX_AMOUNT_EXCEEDED)

    trial = context_for(world, recovery.product)
    verdict = evaluate(trial)
    assert verdict.decision in (Decision.APPROVED, Decision.PENDING_APPROVAL)


def test_category_blocks_are_not_recovered(db, world):
    """The user said they do not want that kind of thing bought. Offering more
    of it is not helpful, it is nagging."""
    assert ReasonCode.CATEGORY_NOT_ALLOWED not in RECOVERABLE

    ctx = context_for(world, world["products"]["subscription"])
    verdict = evaluate(ctx)
    assert verdict.reason_code == ReasonCode.CATEGORY_NOT_ALLOWED

    assert find_recovery(db, ctx, verdict.reason_code) is None


def test_no_offer_when_nothing_in_the_catalog_qualifies(db, world):
    """Cheapest item blocked on price: there is nothing cheaper to offer."""
    lite = world["products"]["lite"]
    ctx = context_for(world, lite)
    # Force the block by shrinking the policy below even the cheapest item.
    world["policy"].max_per_transaction_paise = 100
    db.commit()

    verdict = evaluate(ctx)
    assert verdict.decision == Decision.BLOCKED
    assert find_recovery(db, ctx, verdict.reason_code) is None


def test_recovery_stays_inside_the_original_category(db, world):
    """Someone refused headphones wants headphones, not groceries that happen
    to fit the budget."""
    ctx = context_for(world, world["products"]["premium"])
    recovery = find_recovery(db, ctx, ReasonCode.MAX_AMOUNT_EXCEEDED)

    assert recovery.product.category == world["products"]["premium"].category


def test_blocked_transaction_carries_the_offer_end_to_end(db, world):
    """Through the real request path, not just the helper."""
    from app.services.gateway import handle_purchase_request

    txn, _ = handle_purchase_request(
        db, world["agent"],
        product_id=world["products"]["premium"].id,
        idempotency_key="recovery_e2e_001",
    )

    assert txn.decision == Decision.BLOCKED
    assert txn.recovery is not None
    assert txn.recovery["name"] == "SoundBeat Pro"
    assert txn.recovery["price_paise"] == 179900

    # Still blocked. An offer is not an approval.
    assert txn.state == "BLOCKED"
    assert txn.budget_reserved is False


def test_the_offer_is_audited(db, world):
    from app.services import audit
    from app.services.gateway import handle_purchase_request

    txn, _ = handle_purchase_request(
        db, world["agent"],
        product_id=world["products"]["premium"].id,
        idempotency_key="recovery_audit_001",
    )

    events = [e.event_type for e in audit.trail(db, txn.id)]
    assert "RECOVERY_OFFERED" in events
    assert audit.verify_chain(db, txn.id)["valid"]
