"""Transactions, their audit trails, and the one endpoint that can pay."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import TransactionRequest
from app.schemas.api import (
    AuditEntryOut,
    AuditTrailOut,
    PaymentCreateIn,
    TransactionView,
)
from app.services import audit, events
from app.services.payments_flow import PaymentNotAllowed, create_payment

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionView])
def list_transactions(
    db: DbSession,
    user: CurrentUser,
    state: str | None = None,
    decision: str | None = None,
    limit: int = 50,
):
    query = select(TransactionRequest).where(TransactionRequest.user_id == user.id)
    if state:
        # Comma-separated so a UI filter can span several lifecycle states.
        # "Authorized", for instance, has to cover APPROVED and the payment
        # states that follow it, or the tab empties the moment you pay.
        wanted = [s.strip() for s in state.split(",") if s.strip()]
        query = query.where(TransactionRequest.state.in_(wanted))
    if decision:
        query = query.where(TransactionRequest.decision == decision)

    rows = db.scalars(
        query.order_by(TransactionRequest.created_at.desc()).limit(min(limit, 200))
    )
    return [TransactionView.build(t) for t in rows]


@router.get("/{transaction_id}", response_model=TransactionView)
def get_transaction(transaction_id: str, db: DbSession, user: CurrentUser):
    txn = db.get(TransactionRequest, transaction_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such transaction.")
    return TransactionView.build(txn)


@router.get("/{transaction_id}/audit", response_model=AuditTrailOut)
def get_audit_trail(transaction_id: str, db: DbSession, user: CurrentUser):
    """The full history, plus a verification of the hash chain.

    The integrity block is the point: it lets a reviewer confirm the trail has
    not been rewritten, rather than asking them to take it on faith.
    """
    txn = db.get(TransactionRequest, transaction_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such transaction.")

    entries = audit.trail(db, transaction_id)
    return AuditTrailOut(
        transaction_id=transaction_id,
        entries=[AuditEntryOut.model_validate(e) for e in entries],
        integrity=audit.verify_chain(db, transaction_id),
    )


@router.post("/{transaction_id}/payment", response_model=TransactionView)
def create_transaction_payment(
    transaction_id: str,
    payload: PaymentCreateIn,
    db: DbSession,
    user: CurrentUser,
):
    """Create a payment order.

    The only route to money in the entire system, and it re-verifies
    authorization against the database before doing anything. A BLOCKED,
    REJECTED, EXPIRED or still-PENDING transaction is refused with 409.
    """
    txn = db.get(TransactionRequest, transaction_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such transaction.")

    try:
        txn = create_payment(db, transaction_id, force_failure=payload.force_failure)
    except PaymentNotAllowed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    events.publish(
        "transaction.payment",
        {"transaction_id": txn.id, "state": txn.state, "order_id": txn.payment_order_id},
    )
    return TransactionView.build(txn)
