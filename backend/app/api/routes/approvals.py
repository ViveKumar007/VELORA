"""The approval centre: where a human decides."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import ApprovalDecision, ApprovalRequest, TransactionRequest
from app.schemas.api import ApprovalOut, RejectIn, TransactionOut, TransactionView
from app.services import events
from app.services.approvals import (
    ApprovalError,
    approve,
    expire_stale_approvals,
    reject,
)
from app.utils.money import format_inr

router = APIRouter(prefix="/api", tags=["approvals"])


@router.get("/approvals", response_model=list[ApprovalOut])
def list_pending_approvals(db: DbSession, user: CurrentUser):
    """Pending approvals, with anything past its deadline swept first.

    Sweeping on read means expiry is visibly correct in a demo without
    running a background worker.
    """
    expire_stale_approvals(db)

    rows = db.scalars(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.user_id == user.id,
            ApprovalRequest.decision == ApprovalDecision.PENDING,
        )
        .order_by(ApprovalRequest.created_at.asc())
    )

    out: list[ApprovalOut] = []
    for approval in rows:
        txn = db.get(TransactionRequest, approval.transaction_id)
        if txn is None:
            continue
        out.append(
            ApprovalOut(
                id=approval.id,
                transaction_id=approval.transaction_id,
                decision=approval.decision,
                prompt=approval.prompt,
                expires_at=approval.expires_at,
                created_at=approval.created_at,
                transaction=TransactionOut.model_validate(txn),
                amount_display=format_inr(txn.requested_amount_paise),
            )
        )
    return out


@router.post("/transactions/{transaction_id}/approve", response_model=TransactionView)
def approve_transaction(transaction_id: str, db: DbSession, user: CurrentUser):
    txn = db.get(TransactionRequest, transaction_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such transaction.")

    try:
        txn = approve(db, transaction_id, user_id=user.id)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    events.publish(
        "transaction.approved", {"transaction_id": txn.id, "state": txn.state}
    )
    return TransactionView.build(txn)


@router.post("/transactions/{transaction_id}/reject", response_model=TransactionView)
def reject_transaction(
    transaction_id: str, payload: RejectIn, db: DbSession, user: CurrentUser
):
    txn = db.get(TransactionRequest, transaction_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such transaction.")

    try:
        txn = reject(db, transaction_id, user_id=user.id, note=payload.note)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    events.publish(
        "transaction.rejected", {"transaction_id": txn.id, "state": txn.state}
    )
    return TransactionView.build(txn)
