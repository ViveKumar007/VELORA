"""Turning refusals into sales.

A guardrail that only ever says no costs the merchant every sale it blocks.
But most blocks are not "you may not shop here" -- they are "not *that* one".
An agent that asked for a 2,499 pair of headphones against a 2,000 limit is a
buyer with intent and budget, and the merchant should not lose them.

So when the gate blocks on price or merchant scope, Velora looks for the best
alternative that the *same policy* would approve, and returns it with the
refusal. The buyer gets an offer they are actually allowed to accept.

The critical property: every candidate is run through the real gate before it
is offered. Suggesting something that would itself be blocked would be worse
than suggesting nothing -- it would teach the buyer the refusals are noise.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gate import EvalContext, ReasonCode, evaluate
from app.models import Decision, Product
from app.utils.money import format_inr

#: Blocks worth recovering from. A category refusal is deliberately absent:
#: the user said they do not want that kind of thing bought, so offering more
#: of it is not helpful, it is nagging.
RECOVERABLE = {
    ReasonCode.MAX_AMOUNT_EXCEEDED,
    ReasonCode.BUDGET_EXCEEDED,
    ReasonCode.MERCHANT_NOT_ALLOWED,
}


@dataclass
class Recovery:
    product: Product
    verdict_decision: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product.id,
            "name": self.product.name,
            "price_paise": self.product.price_paise,
            "price_display": format_inr(self.product.price_paise),
            "merchant": self.product.merchant,
            "category": self.product.category,
            "rating": self.product.rating,
            "attributes": self.product.attributes or {},
            "would_be": self.verdict_decision,
            "explanation": self.explanation,
        }


def _candidates(db: Session, blocked: Product, reason: ReasonCode) -> list[Product]:
    """Narrow the catalog to plausible substitutes for what was refused."""
    query = select(Product).where(
        Product.in_stock.is_(True),
        Product.id != blocked.id,
        # Stay in the same category: someone refused headphones wants
        # headphones, not groceries that happen to fit the budget.
        Product.category == blocked.category,
    )

    if reason == ReasonCode.MERCHANT_NOT_ALLOWED:
        # Same goods, a merchant the policy actually permits.
        query = query.where(Product.merchant != blocked.merchant)
    else:
        # Priced out: only cheaper options can possibly clear the limit.
        query = query.where(Product.price_paise < blocked.price_paise)

    return list(db.scalars(query))


def find_recovery(
    db: Session, ctx: EvalContext, reason: ReasonCode
) -> Recovery | None:
    """Best alternative the same policy would approve, or None.

    Ranked by price descending among those that pass: the closest thing to
    what the buyer originally wanted, not the cheapest thing available. A
    buyer refused a 2,499 item is better served by a 1,799 one than a 199 one.
    """
    if reason not in RECOVERABLE or ctx.policy is None or ctx.product is None:
        return None

    candidates = _candidates(db, ctx.product, reason)
    if not candidates:
        return None

    approved: list[tuple[Product, str, str]] = []
    for candidate in sorted(candidates, key=lambda p: p.price_paise, reverse=True):
        # Re-run the real gate. An offer that would itself be refused is worse
        # than no offer at all.
        trial = EvalContext(
            agent=ctx.agent,
            now=ctx.now,
            policy=ctx.policy,
            product=candidate,
            amount_paise=candidate.price_paise,
            currency=candidate.currency,
            category=candidate.category,
            merchant=candidate.merchant,
            claimed_agent_id=ctx.claimed_agent_id,
        )
        verdict = evaluate(trial)
        if verdict.decision in (Decision.APPROVED, Decision.PENDING_APPROVAL):
            approved.append((candidate, str(verdict.decision), verdict.explanation))
            break  # sorted by price desc, so the first pass is the best fit

    if not approved:
        return None

    product, decision, _ = approved[0]
    if decision == Decision.PENDING_APPROVAL:
        note = "and would be held for your approval"
    else:
        note = "and would be approved automatically"

    return Recovery(
        product=product,
        verdict_decision=decision,
        explanation=(
            f"{product.name} at {format_inr(product.price_paise)} from "
            f"{product.merchant} is within this authorization {note}."
        ),
    )
