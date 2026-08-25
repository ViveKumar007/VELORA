"""The shopping agent.

It reads a goal, searches the catalog, ranks what it finds and picks one
item. Then it stops. It cannot pay, cannot see the policy, and cannot learn
whether it is allowed to buy what it chose except by asking Velora and being
told.

That blindness is intentional. An agent that could read the policy would be
tempted to route around it; an agent that can only propose is one whose
authority is defined entirely outside itself.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.intent import ShoppingIntent, extract_intent
from app.agent.scoring import ScoredProduct, rank
from app.models import Product
from app.utils.money import format_inr


@dataclass
class Recommendation:
    intent: ShoppingIntent
    chosen: ScoredProduct | None
    alternatives: list[ScoredProduct]
    rationale: str

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.to_dict(),
            "chosen": self.chosen.to_dict() if self.chosen else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "rationale": self.rationale,
        }


def _search(db: Session, intent: ShoppingIntent) -> list[Product]:
    """Narrow the catalog by category when the intent names one, then fall
    back to everything rather than returning nothing."""
    query = select(Product).where(Product.in_stock.is_(True))
    if intent.category:
        narrowed = list(db.scalars(query.where(Product.category == intent.category)))
        if narrowed:
            return narrowed
    return list(db.scalars(query))


def _rationale(chosen: ScoredProduct, intent: ShoppingIntent) -> str:
    product = chosen.product
    reasons = ", ".join(chosen.notes) if chosen.notes else "best overall match"
    budget_note = (
        f" against your {format_inr(intent.max_budget_paise)} budget"
        if intent.max_budget_paise
        else ""
    )
    return (
        f"Selected {product.name} at {format_inr(product.price_paise)}{budget_note} "
        f"because it offers {reasons}."
    )


def recommend(db: Session, goal: str) -> Recommendation:
    """Pick the best available product for a plain-language goal."""
    intent = extract_intent(goal)
    ranked = rank(_search(db, intent), intent)

    if not ranked:
        return Recommendation(
            intent=intent,
            chosen=None,
            alternatives=[],
            rationale="No product in the catalog matches this request.",
        )

    chosen = ranked[0]
    return Recommendation(
        intent=intent,
        chosen=chosen,
        alternatives=ranked[1:4],
        rationale=_rationale(chosen, intent),
    )
