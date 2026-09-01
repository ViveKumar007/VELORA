"""Buying a recipe, not a product.

`recommend()` answers "what one thing should I buy?" and collapses everything
to a single winner. That is the wrong shape for "I want all the ingredients
to make biryani": the answer is a list, one line per ingredient, and the
interesting part is which ingredients the catalog cannot fill at all.

So this module keeps the ingredients apart. For each item the intent asked
for, it searches the catalog on that item alone and picks the best match for
it. Rice is judged against rice, not against onions.

It proposes and stops. Nothing here decides whether the basket may be bought
-- it does not read a policy, does not know a limit, and cannot create a
payment. The basket goes to the same gate every single purchase goes to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.intent import ShoppingIntent
from app.agent.matching import find_relevant, query_terms
from app.agent.scoring import rank
from app.agent.understanding import understand
from app.models import Product
from app.utils.money import format_inr

OK = "ok"
NO_MATCH = "no_match"
NEEDS_CLARIFICATION = "needs_clarification"

#: How many swap options to offer per line. Enough to change your mind,
#: few enough to stay a shopping list rather than a search results page.
ALTERNATIVES_PER_LINE = 3

#: How many of the most-relevant candidates go forward to scoring.
#:
#: Relevance and quality answer different questions and must be applied in
#: that order. Handing every match straight to rank() sorted them by rating,
#: which put "Garden Onion Pakoda Namkeen" (a 4.5-rated snack) above a plain
#: onion -- scoring did its job perfectly on a candidate set that should never
#: have included the snack. So relevance filters first, and rating only
#: chooses between things that are genuinely the requested item.
RELEVANCE_POOL = 5


@dataclass
class BasketLine:
    """One ingredient, and the product proposed for it."""

    item: str
    product: Product
    score: float
    notes: list[str] = field(default_factory=list)
    alternatives: list[Product] = field(default_factory=list)

    def to_dict(self) -> dict:
        def brief(p: Product) -> dict:
            return {
                "product_id": p.id,
                "name": p.name,
                "price_paise": p.price_paise,
                "price_display": format_inr(p.price_paise),
                "merchant": p.merchant,
                "category": p.category,
                "rating": p.rating,
                "quantity": (p.attributes or {}).get("quantity", ""),
            }

        return {
            "item": self.item,
            **brief(self.product),
            "score": round(self.score, 4),
            "notes": list(self.notes),
            "alternatives": [brief(p) for p in self.alternatives],
        }


@dataclass
class Basket:
    intent: ShoppingIntent
    lines: list[BasketLine]
    unavailable: list[str]
    status: str = OK
    message: str = ""

    @property
    def total_paise(self) -> int:
        return sum(line.product.price_paise for line in self.lines)

    @property
    def merchants(self) -> list[str]:
        return sorted({line.product.merchant for line in self.lines})

    @property
    def categories(self) -> list[str]:
        return sorted({line.product.category for line in self.lines})

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.to_dict(),
            "status": self.status,
            "message": self.message,
            "lines": [line.to_dict() for line in self.lines],
            "unavailable": list(self.unavailable),
            "total_paise": self.total_paise,
            "total_display": format_inr(self.total_paise),
            "merchants": self.merchants,
            "categories": self.categories,
            "clarification": self.intent.clarification,
        }


def _catalog(db: Session) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.in_stock.is_(True))))


def recommend_basket(db: Session, goal: str) -> Basket:
    """Turn a goal into a shopping list the catalog can actually fill."""
    intent = understand(db, goal)

    if intent.needs_clarification:
        return Basket(
            intent=intent,
            lines=[],
            unavailable=[],
            status=NEEDS_CLARIFICATION,
            message=intent.clarification
            or "That request is ambiguous. What would you like to buy?",
        )

    catalog = _catalog(db)

    # Gemini names the ingredients. The rules parser does not, and leaves
    # required_items empty for anything that is not a dish it knows -- so
    # "milk and bread" would have produced a one-line basket. Fall back to
    # the nouns in the request, keeping only those the catalog can answer,
    # which keeps baskets working with the model switched off.
    items = list(intent.required_items or [])
    if not items:
        items = [
            term
            for term in query_terms(intent.product_query or goal)
            if find_relevant(catalog, items=[term])
        ]
    lines: list[BasketLine] = []
    unavailable: list[str] = []
    used: set[str] = set()

    for item in items:
        matches = find_relevant(catalog, items=[item])
        if not matches:
            unavailable.append(item)
            continue

        # Relevance decides which product answers this ingredient; scoring
        # only describes it.
        #
        # Letting rank() choose was wrong even after filtering to the top
        # candidates: it sorts by rating, so a 4.5-rated onion-flavoured
        # snack beat a plain onion that happened to carry no rating at all.
        # For a shopping list, "is actually the thing asked for" outranks
        # "is well reviewed" every time. Cheaper or better-rated options are
        # still one click away as alternatives.
        pool = [m.product for m in matches[:RELEVANCE_POOL]]
        # One product cannot answer two ingredients: "tomato" and "tomato
        # sauce" would otherwise resolve to the same bottle and be charged
        # for twice.
        product = next((p for p in pool if p.id not in used), None)
        if product is None:
            unavailable.append(item)
            continue

        scored = {s.product.id: s for s in rank(pool, intent)}
        used.add(product.id)
        lines.append(
            BasketLine(
                item=item,
                product=product,
                score=scored[product.id].score if product.id in scored else 0.0,
                notes=list(scored[product.id].notes) if product.id in scored else [],
                alternatives=[p for p in pool if p.id != product.id][:ALTERNATIVES_PER_LINE],
            )
        )

    if not lines:
        return Basket(
            intent=intent,
            lines=[],
            unavailable=unavailable,
            status=NO_MATCH,
            message=(
                f"Nothing in the catalog covers {', '.join(unavailable)}."
                if unavailable
                else "Nothing in the catalog matches this request."
            ),
        )

    message = ""
    if unavailable:
        message = (
            f"{len(lines)} of {len(lines) + len(unavailable)} items found. "
            f"No merchant stocks: {', '.join(unavailable)}."
        )

    return Basket(
        intent=intent,
        lines=lines,
        unavailable=unavailable,
        status=OK,
        message=message,
    )
