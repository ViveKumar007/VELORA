"""The request path: agent asks, Velora decides.

Everything below happens inside ONE database transaction, which is what makes
the guarantees hold:

  * the unique index on (agent_id, idempotency_key) arbitrates duplicate
    requests, so two identical calls cannot both create work;
  * the policy row is held FOR UPDATE across evaluation and reservation, so
    concurrent requests cannot both pass the same quota check;
  * budget is reserved in the same transaction that records the decision, so
    a decision can never exist without its accounting;
  * audit entries commit with the change they describe, never separately.

The agent supplies exactly two things: which product it wants, and an
idempotency key. Price, category and merchant are read from Velora's own
catalog. An agent that misreports a category therefore changes nothing --
there is no field for it to lie in.
"""

import hashlib
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.agent.recovery import find_recovery
from app.gate import EvalContext, evaluate
from app.models import (
    Agent,
    ApprovalRequest,
    Decision,
    EventType,
    Product,
    TransactionRequest,
    TxnState,
    utcnow,
)
from app.services import audit, budget
from app.services.state_machine import assert_transition
from app.utils.money import format_inr


class IdempotencyConflict(Exception):
    """Same idempotency key, different request.

    Returning the original result would be wrong (the caller asked for
    something else) and creating a new transaction would defeat the key. The
    only honest answer is to refuse.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"Idempotency key '{key}' was already used for a different request payload."
        )


def _fingerprint(agent_id: str, product_id: str, currency: str) -> str:
    body = json.dumps(
        {"agent_id": agent_id, "product_id": product_id, "currency": currency},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()


def _snapshot_policy(policy) -> dict:
    """Freeze the policy exactly as evaluated.

    Without this, a user who raises a limit after a block leaves an audit
    trail that reads 'blocked, limit 2000' next to a policy that now says
    5000, and the record can no longer be verified.
    """
    return {
        "id": policy.id,
        "name": policy.name,
        "max_per_transaction_paise": policy.max_per_transaction_paise,
        "total_budget_paise": policy.total_budget_paise,
        "approval_threshold_paise": policy.approval_threshold_paise,
        "currency": policy.currency,
        "allowed_categories": list(policy.allowed_categories or []),
        "allowed_merchants": list(policy.allowed_merchants or []),
        "max_transactions": policy.max_transactions,
        "one_time_use": policy.one_time_use,
        "transactions_used_at_eval": policy.transactions_used,
        "amount_reserved_at_eval": policy.amount_reserved_paise,
        "amount_settled_at_eval": policy.amount_settled_paise,
        "valid_from": policy.valid_from.isoformat(),
        "expires_at": policy.expires_at.isoformat(),
        "status_at_eval": policy.status,
    }


def move_state(
    db: Session,
    txn: TransactionRequest,
    target: TxnState,
    *,
    event_type: EventType,
    actor: str = "system",
    explanation: str = "",
    decision: str | None = None,
    reason_code: str | None = None,
    metadata: dict | None = None,
) -> None:
    """The only sanctioned way to change a transaction's state."""
    assert_transition(txn.state, target)
    previous = txn.state
    txn.state = str(target)
    audit.record(
        db,
        event_type=event_type,
        transaction_id=txn.id,
        agent_id=txn.agent_id,
        policy_id=txn.policy_id,
        actor=actor,
        decision=decision,
        reason_code=reason_code,
        explanation=explanation,
        previous_state=previous,
        new_state=str(target),
        metadata=metadata or {},
    )


def handle_purchase_request(
    db: Session,
    agent: Agent,
    *,
    product_id: str,
    idempotency_key: str,
    claimed_agent_id: str | None = None,
    agent_rationale: str | None = None,
    currency: str = "INR",
) -> tuple[TransactionRequest, bool]:
    """Evaluate one purchase request. Returns (transaction, was_replayed)."""
    now = utcnow()
    fingerprint = _fingerprint(agent.id, product_id, currency)

    # --- Idempotency, fast path -------------------------------------------
    existing = db.scalars(
        select(TransactionRequest).where(
            TransactionRequest.agent_id == agent.id,
            TransactionRequest.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        return _replay(db, existing, fingerprint, idempotency_key), True

    product = db.get(Product, product_id)

    txn = TransactionRequest(
        agent_id=agent.id,
        user_id=agent.user_id,
        product_id=product.id if product else None,
        product_name=product.name if product else "(unknown product)",
        merchant=product.merchant if product else "",
        category=product.category if product else "",
        requested_amount_paise=product.price_paise if product else 0,
        currency=(product.currency if product else currency),
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        state=str(TxnState.CREATED),
        agent_rationale=agent_rationale,
    )

    # --- Idempotency, race path -------------------------------------------
    # Two identical requests can both miss the fast path. The unique index
    # settles it: exactly one insert survives, the loser replays the winner.
    savepoint = db.begin_nested()
    try:
        db.add(txn)
        db.flush()
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        winner = db.scalars(
            select(TransactionRequest).where(
                TransactionRequest.agent_id == agent.id,
                TransactionRequest.idempotency_key == idempotency_key,
            )
        ).first()
        if winner is None:
            raise
        replayed = _replay(db, winner, fingerprint, idempotency_key)
        db.commit()
        return replayed, True

    audit.record(
        db,
        event_type=EventType.REQUEST_RECEIVED,
        transaction_id=txn.id,
        agent_id=agent.id,
        actor=agent.id,
        explanation=(
            f"Agent {agent.name} requested {txn.product_name}"
            + (f" for {format_inr(txn.requested_amount_paise)}" if product else "")
            + "."
        ),
        new_state=str(TxnState.CREATED),
        metadata={
            "product_id": product_id,
            "idempotency_key": idempotency_key,
            "agent_rationale": agent_rationale,
        },
    )

    # --- Evaluate under a policy row lock ---------------------------------
    policy = budget.active_policy_for_agent(db, agent.id)
    if policy is not None:
        txn.policy_id = policy.id
        txn.policy_snapshot = _snapshot_policy(policy)

    move_state(
        db, txn, TxnState.EVALUATING,
        event_type=EventType.EVALUATION_STARTED,
        explanation="Policy evaluation started.",
    )

    ctx = EvalContext(
        agent=agent,
        now=now,
        policy=policy,
        product=product,
        amount_paise=txn.requested_amount_paise,
        currency=txn.currency,
        category=txn.category,
        merchant=txn.merchant,
        claimed_agent_id=claimed_agent_id,
    )
    verdict = evaluate(ctx)

    txn.decision = str(verdict.decision)
    txn.reason_code = str(verdict.reason_code)
    txn.explanation = verdict.explanation
    txn.checks = verdict.checks_as_dicts()
    txn.decided_at = now

    for result in verdict.checks:
        if result.status == "SKIP":
            continue
        audit.record(
            db,
            event_type=EventType.CHECK_EVALUATED,
            transaction_id=txn.id,
            agent_id=agent.id,
            policy_id=txn.policy_id,
            decision=str(result.status),
            reason_code=str(result.reason_code) if result.reason_code else None,
            explanation=f"{result.name}: {result.detail}",
            metadata={"check": result.name, "status": str(result.status)},
        )

    # --- Apply the decision -----------------------------------------------
    if verdict.decision == Decision.BLOCKED:
        # A refusal on price or merchant scope is not the end of the sale.
        # Look for something this same policy would approve and offer it, so
        # the merchant keeps a buyer who has both intent and budget.
        recovery = find_recovery(db, ctx, verdict.reason_code)
        if recovery is not None:
            txn.recovery = recovery.to_dict()

        move_state(
            db, txn, TxnState.BLOCKED,
            event_type=EventType.DECISION_MADE,
            decision=str(verdict.decision),
            reason_code=str(verdict.reason_code),
            explanation=verdict.explanation,
        )
        if recovery is not None:
            audit.record(
                db,
                event_type=EventType.RECOVERY_OFFERED,
                transaction_id=txn.id,
                agent_id=agent.id,
                policy_id=txn.policy_id,
                explanation=(
                    f"Blocked, but an in-policy alternative was offered: {recovery.explanation}"
                ),
                previous_state=str(TxnState.BLOCKED),
                new_state=str(TxnState.BLOCKED),
                metadata=txn.recovery,
            )
        db.commit()
        return txn, False

    # Approved or escalated: both commit budget before the transaction can
    # progress, so pending approvals cannot collectively exceed the budget.
    budget.reserve(db, policy, txn)
    audit.record(
        db,
        event_type=EventType.BUDGET_RESERVED,
        transaction_id=txn.id,
        agent_id=agent.id,
        policy_id=policy.id,
        explanation=(
            f"Reserved {format_inr(txn.requested_amount_paise)}; "
            f"{format_inr(policy.remaining_budget_paise)} of "
            f"{format_inr(policy.total_budget_paise)} remains."
        ),
        metadata={
            "reserved_paise": txn.requested_amount_paise,
            "remaining_paise": policy.remaining_budget_paise,
            "transactions_used": policy.transactions_used,
        },
    )

    if verdict.decision == Decision.PENDING_APPROVAL:
        move_state(
            db, txn, TxnState.PENDING_APPROVAL,
            event_type=EventType.DECISION_MADE,
            decision=str(verdict.decision),
            reason_code=str(verdict.reason_code),
            explanation=verdict.explanation,
        )
        db.add(
            ApprovalRequest(
                transaction_id=txn.id,
                user_id=agent.user_id,
                prompt=verdict.explanation,
                expires_at=now + timedelta(minutes=settings.approval_ttl_minutes),
            )
        )
        db.flush()
    else:
        move_state(
            db, txn, TxnState.APPROVED,
            event_type=EventType.DECISION_MADE,
            decision=str(verdict.decision),
            reason_code=str(verdict.reason_code),
            explanation=verdict.explanation,
        )

    db.commit()
    return txn, False


def _replay(
    db: Session,
    existing: TransactionRequest,
    fingerprint: str,
    idempotency_key: str,
) -> TransactionRequest:
    """Return a previously decided transaction instead of doing the work twice."""
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflict(idempotency_key)

    audit.record(
        db,
        event_type=EventType.DUPLICATE_SUPPRESSED,
        transaction_id=existing.id,
        agent_id=existing.agent_id,
        policy_id=existing.policy_id,
        actor=existing.agent_id,
        decision=existing.decision,
        reason_code=existing.reason_code,
        explanation=(
            "Duplicate request with a known idempotency key. Returned the original "
            "decision; no second payment was created."
        ),
        previous_state=existing.state,
        new_state=existing.state,
        metadata={"idempotency_key": idempotency_key},
    )
    db.commit()
    return existing
