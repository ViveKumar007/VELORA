"""Merchants, and the machine-readable catalog that makes them transactable.

A merchant wants revenue from AI buyers but cannot accept unbounded agent
spend. These endpoints are the two halves of solving that:

  GET /api/merchants/catalog   what an AI buyer reads to decide what to buy
  GET /api/merchants/{slug}    what a human reads about one seller

The catalog is deliberately explicit about how to transact. An agent should
not have to guess the purchase protocol, and it should learn up front that
every purchase is gated -- so a refusal is an expected outcome to handle, not
an error to retry blindly.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentMerchant, DbSession
from app.models import Merchant, Product, TxnState, TransactionRequest
from app.schemas.api import AgentCatalog, MerchantOut, MerchantSelf, MerchantStats
from app.utils.money import format_inr

router = APIRouter(prefix="/api/merchants", tags=["merchants"])


@router.get("/catalog", response_model=AgentCatalog)
def agent_catalog(db: DbSession, category: str | None = None, merchant: str | None = None):
    """The agent-readable catalog.

    One document an autonomous buyer can fetch to learn what is for sale and
    exactly how to buy it. Prices are integer paise so no client has to guess
    a unit, and every item carries the merchant and category the gate will
    judge it on -- an agent can therefore predict a refusal before making one.
    """
    query = select(Product).where(Product.in_stock.is_(True))
    if category:
        query = query.where(Product.category == category)
    if merchant:
        query = query.where(Product.merchant == merchant)

    products = list(db.scalars(query.order_by(Product.price_paise.asc())))
    merchants = list(db.scalars(select(Merchant).where(Merchant.status == "ACTIVE")))

    return AgentCatalog(
        version="1.0",
        currency="INR",
        amount_unit="paise",
        merchants=[MerchantOut.model_validate(m) for m in merchants],
        items=[
            {
                "product_id": p.id,
                "name": p.name,
                "description": p.description,
                "price_paise": p.price_paise,
                "price_display": format_inr(p.price_paise),
                "currency": p.currency,
                "category": p.category,
                "merchant": p.merchant,
                "rating": p.rating,
                "attributes": p.attributes or {},
            }
            for p in products
        ],
        purchase_protocol={
            "endpoint": "POST /api/agent/request",
            "authentication": "Authorization: Bearer <agent token>",
            "request_body": {
                "product_id": "<product_id from this catalog>",
                "idempotency_key": "<unique per purchase intent, 8-120 chars>",
            },
            "note": (
                "Send only the product_id. Price, category and merchant are read "
                "from this catalog server-side and cannot be supplied by the buyer."
            ),
            "possible_decisions": ["APPROVED", "PENDING_APPROVAL", "BLOCKED"],
            "on_blocked": (
                "The response may carry a `recovery` object: an in-policy "
                "alternative already checked against the same authorization. "
                "Re-request with that product_id and a new idempotency_key."
            ),
            "payment": "POST /api/transactions/{id}/payment, approved transactions only",
        },
    )


@router.get("", response_model=list[MerchantOut])
def list_merchants(db: DbSession):
    return list(db.scalars(select(Merchant).order_by(Merchant.name.asc())))


@router.get("/me", response_model=MerchantStats)
def merchant_console(merchant: CurrentMerchant, db: DbSession):
    """The signed-in merchant's own console.

    Scoped to the session, never to a path parameter: revenue is nobody
    else's business, and a public /{slug}/stats would have published every
    seller's takings to anyone who could guess a slug.

    recovery_offered is the number that matters here: purchases the gate
    refused where an in-policy alternative was offered instead. Those are
    sales a plain guardrail would simply have lost.
    """

    def count(*where) -> int:
        return db.scalar(
            select(func.count())
            .select_from(TransactionRequest)
            .where(TransactionRequest.merchant == merchant.name, *where)
        ) or 0

    settled = db.scalar(
        select(func.coalesce(func.sum(TransactionRequest.requested_amount_paise), 0)).where(
            TransactionRequest.merchant == merchant.name,
            TransactionRequest.state == TxnState.PAYMENT_SUCCESS,
        )
    ) or 0

    blocked = count(TransactionRequest.state == TxnState.BLOCKED)
    offered = count(
        TransactionRequest.state == TxnState.BLOCKED,
        TransactionRequest.recovery.isnot(None),
    )

    return MerchantStats(
        merchant=MerchantSelf.model_validate(merchant),
        products=db.scalar(
            select(func.count()).select_from(Product).where(Product.merchant == merchant.name)
        ) or 0,
        paid=count(TransactionRequest.state == TxnState.PAYMENT_SUCCESS),
        revenue_paise=settled,
        revenue_display=format_inr(settled),
        blocked=blocked,
        recovery_offered=offered,
    )


@router.get("/{slug}", response_model=MerchantOut)
def merchant_profile(slug: str, db: DbSession):
    """Public profile. Deliberately no revenue figures -- those live behind
    the merchant's own session at /api/merchants/me."""
    merchant = db.scalars(select(Merchant).where(Merchant.slug == slug)).first()
    if merchant is None:
        raise HTTPException(status_code=404, detail="No such merchant.")
    return merchant
