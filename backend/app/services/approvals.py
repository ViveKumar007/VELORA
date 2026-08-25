"""Human decisions on escalated transactions.

Approve, reject and expire all take the transaction row under a lock, verify
the transaction is genuinely awaiting a human, and act exactly once. Clicking
Approve twice cannot approve twice; approving something the sweeper already
expired is refused rather than silently accepted.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ApprovalDecision,
    ApprovalRequest,
    EventType,
    TransactionRequest,
    TxnState,
    utcnow,
)
from app.services import audit, budget
from app.services.gateway import move_state
from app.utils.money import format_inr


class ApprovalError(Exception):
    """The approval cannot be acted on as requested."""


def _lock_transaction(db: Session, transaction_id: str) -> TransactionRequest:
    txn = db.scalars(
        select(TransactionRequest)
        .where(TransactionRequest.id == transaction_id)
        .with_for_update()
    ).first()
    if txn is None:
        raise ApprovalError(f"Transaction {transaction_id} does not exist.")
    return txn


def _load_approval(db: Session, transaction_id: str) -> ApprovalRequest:
    approval = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.transaction_id == transaction_id)
        .with_for_update()
    ).first()
    if approval is None:
        raise ApprovalError("This transaction has no pending approval.")
    return approval


def approve(db: Session, transaction_id: str, *, user_id: str) -> TransactionRequest:
    txn = _lock_transaction(db, transaction_id)
    approval = _load_approval(db, transaction_id)
    now = utcnow()

    if txn.state != TxnState.PENDING_APPROVAL:
        raise ApprovalError(
            f"This transaction is {txn.state} and is no longer awaiting approval."
        )
    if approval.decision != ApprovalDecision.PENDING:
        raise ApprovalError(f"This approval was already {approval.decision.lower()}.")
    if now >= approval.expires_at:
        # Lazy expiry: a stale approval must not be actionable just because
        # the sweeper has not run yet.
        _expire(db, txn, approval, now)
        db.commit()
        raise ApprovalError("This approval request expired before it was actioned.")

    approval.decision = str(ApprovalDecision.APPROVED)
    approval.decided_by = user_id
    approval.decided_at = now

    move_state(
        db, txn, TxnState.APPROVED,
        event_type=EventType.HUMAN_APPROVED,
        actor=user_id,
        decision=str(ApprovalDecision.APPROVED),
        explanation=(
            f"User approved {txn.product_name} for "
            f"{format_inr(txn.requested_amount_paise)}."
        ),
    )
    db.commit()
    return txn


def reject(
    db: Session, transaction_id: str, *, user_id: str, note: str | None = None
) -> TransactionRequest:
    txn = _lock_transaction(db, transaction_id)
    approval = _load_approval(db, transaction_id)
    now = utcnow()

    if txn.state != TxnState.PENDING_APPROVAL:
        raise ApprovalError(
            f"This transaction is {txn.state} and is no longer awaiting approval."
        )
    if approval.decision != ApprovalDecision.PENDING:
        raise ApprovalError(f"This approval was already {approval.decision.lower()}.")

    approval.decision = str(ApprovalDecision.REJECTED)
    approval.decided_by = user_id
    approval.decided_at = now

    move_state(
        db, txn, TxnState.REJECTED,
        event_type=EventType.HUMAN_REJECTED,
        actor=user_id,
        decision=str(ApprovalDecision.REJECTED),
        explanation=note or f"User rejected {txn.product_name}. No payment was created.",
    )
    _release_hold(db, txn, reason="rejected by user")
    db.commit()
    return txn


def expire_stale_approvals(db: Session) -> int:
    """Sweep approvals past their deadline.

    Cheap enough to call on any read of the approval queue, so a demo needs
    no background worker to show expiry working.
    """
    now = utcnow()
    stale = list(
        db.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.decision == ApprovalDecision.PENDING,
                ApprovalRequest.expires_at <= now,
            )
        )
    )

    count = 0
    for approval in stale:
        txn = db.get(TransactionRequest, approval.transaction_id)
        if txn is None or txn.state != TxnState.PENDING_APPROVAL:
            continue
        _expire(db, txn, approval, now)
        count += 1

    if count:
        db.commit()
    return count


def _expire(db: Session, txn: TransactionRequest, approval: ApprovalRequest, now) -> None:
    approval.decision = str(ApprovalDecision.EXPIRED)
    approval.decided_at = now
    move_state(
        db, txn, TxnState.EXPIRED,
        event_type=EventType.APPROVAL_EXPIRED,
        explanation=(
            "The approval window closed before anyone responded. The purchase was "
            "abandoned and no payment was created."
        ),
    )
    _release_hold(db, txn, reason="approval expired")


def _release_hold(db: Session, txn: TransactionRequest, *, reason: str) -> None:
    """Give the budget and the transaction slot back."""
    if not txn.budget_reserved or not txn.policy_id:
        return
    policy = budget.lock_policy(db, txn.policy_id)
    if policy is None:
        return

    amount = txn.requested_amount_paise
    budget.release(db, policy, txn)
    audit.record(
        db,
        event_type=EventType.BUDGET_RELEASED,
        transaction_id=txn.id,
        agent_id=txn.agent_id,
        policy_id=policy.id,
        explanation=(
            f"Released {format_inr(amount)} back to the authorization ({reason}). "
            f"{format_inr(policy.remaining_budget_paise)} of "
            f"{format_inr(policy.total_budget_paise)} now available."
        ),
        metadata={
            "released_paise": amount,
            "remaining_paise": policy.remaining_budget_paise,
        },
    )
