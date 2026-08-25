"""Append-only audit trail with a tamper-evident hash chain.

Each entry hashes its own contents together with the hash of the previous
entry for the same transaction. Editing any historical row invalidates every
hash that follows it, so verify_chain() can prove the trail has not been
rewritten. That turns "we log things" into something a reviewer can check.

Nothing in this module ever updates or deletes a row.
"""

import hashlib
import json
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import AuditLog, EventType


def _digest(payload: dict[str, Any], prev_hash: str | None) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{prev_hash or ''}|{body}".encode()).hexdigest()


def record(
    db: Session,
    *,
    event_type: EventType | str,
    transaction_id: str | None = None,
    agent_id: str | None = None,
    policy_id: str | None = None,
    actor: str = "system",
    decision: str | None = None,
    reason_code: str | None = None,
    explanation: str = "",
    previous_state: str | None = None,
    new_state: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one entry. Call inside the caller's transaction so the audit
    record commits atomically with the change it describes -- an audit trail
    that can commit without its subject is worse than none."""
    prev = None
    next_seq = 0
    if transaction_id:
        # Serialise appends for this transaction by taking its row lock first.
        #
        # seq and prev_hash are both read-then-write: without the lock, two
        # concurrent requests touching the same transaction (a duplicate
        # request arriving twice, say) read the same MAX(seq), compute the
        # same next value, and one of them dies on uq_audit_txn_seq -- a 500
        # for the caller and a hole in the hash chain.
        #
        # Lock ordering across the codebase is always transaction -> policy,
        # so acquiring it here cannot deadlock against budget.lock_policy.
        db.execute(
            text("SELECT id FROM transaction_requests WHERE id = :tid FOR UPDATE"),
            {"tid": transaction_id},
        )

        prev = db.scalars(
            select(AuditLog)
            .where(AuditLog.transaction_id == transaction_id)
            .order_by(AuditLog.seq.desc())
            .limit(1)
        ).first()
        next_seq = (
            db.scalar(
                select(func.coalesce(func.max(AuditLog.seq), -1)).where(
                    AuditLog.transaction_id == transaction_id
                )
            )
            + 1
        )

    payload = {
        "transaction_id": transaction_id,
        "seq": next_seq,
        "agent_id": agent_id,
        "policy_id": policy_id,
        "actor": actor,
        "event_type": str(event_type),
        "decision": decision,
        "reason_code": reason_code,
        "explanation": explanation,
        "previous_state": previous_state,
        "new_state": new_state,
        "metadata": metadata or {},
    }

    entry = AuditLog(
        transaction_id=transaction_id,
        seq=next_seq,
        agent_id=agent_id,
        policy_id=policy_id,
        actor=actor,
        event_type=str(event_type),
        decision=decision,
        reason_code=reason_code,
        explanation=explanation,
        previous_state=previous_state,
        new_state=new_state,
        event_metadata=metadata or {},
        prev_hash=prev.entry_hash if prev else None,
        entry_hash=_digest(payload, prev.entry_hash if prev else None),
    )
    db.add(entry)
    db.flush()
    return entry


def trail(db: Session, transaction_id: str) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.transaction_id == transaction_id)
            .order_by(AuditLog.seq.asc())
        )
    )


def verify_chain(db: Session, transaction_id: str) -> dict[str, Any]:
    """Recompute every hash in a transaction's trail and report the first
    entry, if any, that fails to match."""
    entries = trail(db, transaction_id)
    prev_hash: str | None = None

    for entry in entries:
        payload = {
            "transaction_id": entry.transaction_id,
            "seq": entry.seq,
            "agent_id": entry.agent_id,
            "policy_id": entry.policy_id,
            "actor": entry.actor,
            "event_type": entry.event_type,
            "decision": entry.decision,
            "reason_code": entry.reason_code,
            "explanation": entry.explanation,
            "previous_state": entry.previous_state,
            "new_state": entry.new_state,
            "metadata": entry.event_metadata,
        }
        expected = _digest(payload, prev_hash)
        if entry.prev_hash != prev_hash or entry.entry_hash != expected:
            return {
                "valid": False,
                "entries": len(entries),
                "broken_at_seq": entry.seq,
                "detail": "Audit entry does not match its recomputed hash.",
            }
        prev_hash = entry.entry_hash

    return {"valid": True, "entries": len(entries), "broken_at_seq": None, "detail": "Chain intact."}
