"""The shopping agent.

It reads a goal, works out what is actually needed, finds the catalog items
that answer it, ranks those, and picks one. Then it stops. It cannot pay,
cannot see the policy, and cannot learn whether it is allowed to buy what it
chose except by asking Velora and being told.

That blindness is intentional. An agent that could read the policy would be
tempted to route around it; an agent that can only propose is one whose
authority is defined entirely outside itself.

Three outcomes, and admitting to the last two is as important as producing
the first:

    ok                  something in the catalog answers the request
    no_match            nothing does, and here is what was missing
    needs_clarification the request could not be read; here is the question

The old version had only the first. Asked for something it did not stock, it
ranked the whole shop by rating and proposed the winner -- so "I want to make
pasta" came back as a pair of ₹2,499 headphones, stated with complete
confidence. Guessing is the one thing a purchasing agent must not do.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.intent import ShoppingIntent
from app.agent.matching import Match, find_relevant, unmatched_items
from app.agent.scoring import ScoredProduct, rank
from app.agent.understanding import understand
from app.models import Product
from app.utils.money import format_inr

OK = "ok"
NO_MATCH = "no_match"
NEEDS_CLARIFICATION = "needs_clarification"


@dataclass
class Recommendation:
    intent: ShoppingIntent
    chosen: ScoredProduct | None
    alternatives: list[ScoredProduct]
    rationale: str
    status: str = OK
    #: Items the request asked for that the catalog cannot answer at all.
    unavailable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.to_dict(),
            "chosen": self.chosen.to_dict() if self.chosen else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "rationale": self.rationale,
            "status": self.status,
            "unavailable": list(self.unavailable),
            # Kept as its own key so the console can show the question
            # without having to infer it from the status.
            "clarification": self.intent.clarification,
        }


def _catalog(db: Session) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.in_stock.is_(True))))


def _rationale(chosen: ScoredProduct, intent: ShoppingIntent, matched: list[str]) -> str:
    product = chosen.product
    reasons = ", ".join(chosen.notes) if chosen.notes else "best overall match"
    budget_note = (
        f" against your {format_inr(intent.max_budget_paise)} budget"
        if intent.max_budget_paise
        else ""
    )
    # Say what in the request this answers. "because it offers rated 4.8" was
    # true of whatever happened to win and told the reader nothing. A bare
    # category match is not worth reporting -- "it covers groceries" says
    # less than nothing.
    covered = [m for m in matched if m != intent.category]
    answers = f" It covers {', '.join(covered)}." if covered else ""
    for_dish = f" for {intent.dish}" if intent.dish else ""
    return (
        f"Selected {product.name} at {format_inr(product.price_paise)}{budget_note}"
        f"{for_dish} because it offers {reasons}.{answers}"
    )


def _no_match_message(intent: ShoppingIntent, missing: list[str]) -> str:
    wanted = missing or intent.required_items
    if intent.dish and wanted:
        return (
            f"Nothing in the catalog covers {', '.join(wanted)}, so a purchase for "
            f"{intent.dish} cannot be proposed. Velora sells only what its merchants "
            f"list, and none of them stock these."
        )
    if wanted:
        return (
            f"Nothing in the catalog matches {', '.join(wanted)}. "
            f"No purchase was proposed rather than substituting something unrelated."
        )
    return (
        "Nothing in the catalog matches this request, so no purchase was proposed."
    )


def recommend(db: Session, goal: str) -> Recommendation:
    """Pick the best available product for a plain-language goal."""
    intent = understand(db, goal)

    if intent.needs_clarification:
        return Recommendation(
            intent=intent,
            chosen=None,
            alternatives=[],
            rationale=intent.clarification
            or "That request is ambiguous. What would you like to buy?",
            status=NEEDS_CLARIFICATION,
        )

    matches: list[Match] = find_relevant(
        _catalog(db),
        items=intent.required_items,
        query=intent.product_query or goal,
        category=intent.category,
    )

    if not matches:
        missing = intent.required_items or []
        return Recommendation(
            intent=intent,
            chosen=None,
            alternatives=[],
            rationale=_no_match_message(intent, missing),
            status=NO_MATCH,
            unavailable=missing,
        )

    # Only relevant products are ranked. Scoring decides which of several
    # sensible answers is best; it is never asked to decide whether an answer
    # is sensible at all.
    by_id = {m.product.id: m for m in matches}
    ranked = rank([m.product for m in matches], intent)

    if not ranked:
        return Recommendation(
            intent=intent,
            chosen=None,
            alternatives=[],
            rationale=_no_match_message(intent, intent.required_items),
            status=NO_MATCH,
            unavailable=intent.required_items,
        )

    chosen = ranked[0]
    matched_for_chosen = by_id[chosen.product.id].matched
    return Recommendation(
        intent=intent,
        chosen=chosen,
        alternatives=ranked[1:4],
        rationale=_rationale(chosen, intent, matched_for_chosen),
        status=OK,
        unavailable=unmatched_items(intent.required_items, matches),
    )
