"""Budget and quota accounting.

Money moves through three buckets on a policy:

    available -> reserved   when the gate approves or escalates a request
    reserved  -> settled    when a payment actually succeeds
    reserved  -> available  when the purchase is rejected, expires, or fails

Reserving at decision time rather than payment time is what stops an agent
from outrunning its own budget: fire five requests at a policy with room for
one, and only the first one reserves. The rest see the reservation and are
blocked.

Every function here must be called while holding a FOR UPDATE lock on the
policy row -- see lock_policy().
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthorizationPolicy, PolicyStatus, TransactionRequest, utcnow


def lock_policy(db: Session, policy_id: str) -> AuthorizationPolicy | None:
    """Re-read a policy under a row lock.

    Everything that mutates counters goes through here. Without the lock, two
    concurrent requests both read transactions_used = 0, both conclude they
    are within a 1-transaction limit, and a single-use authorization spends
    twice.
    """
    return db.scalars(
        select(AuthorizationPolicy)
        .where(AuthorizationPolicy.id == policy_id)
        .with_for_update()
    ).first()


def active_policy_for_agent(db: Session, agent_id: str) -> AuthorizationPolicy | None:
    """The policy the gate will judge against, locked for update.

    Prefers a live ACTIVE policy. If there is none, it deliberately falls back
    to the agent's most recent policy of *any* status and hands that to the
    gate anyway, so the checks can say precisely what went wrong --
    AUTHORIZATION_EXPIRED, AUTHORIZATION_ALREADY_USED, AUTHORIZATION_INACTIVE.

    Filtering those out here would collapse every one of them into the vague
    and slightly misleading NO_AUTHORIZATION, which reserves its real meaning:
    this agent was never granted any authority at all.
    """
    active = db.scalars(
        select(AuthorizationPolicy)
        .where(
            AuthorizationPolicy.agent_id == agent_id,
            AuthorizationPolicy.status == PolicyStatus.ACTIVE,
        )
        .order_by(AuthorizationPolicy.created_at.desc())
        .limit(1)
        .with_for_update()
    ).first()
    if active is not None:
        return active

    return db.scalars(
        select(AuthorizationPolicy)
        .where(AuthorizationPolicy.agent_id == agent_id)
        .order_by(AuthorizationPolicy.created_at.desc())
        .limit(1)
        .with_for_update()
    ).first()


def reserve(db: Session, policy: AuthorizationPolicy, txn: TransactionRequest) -> None:
    """Commit quota and funds to a transaction that passed the gate."""
    if txn.budget_reserved:
        return
    policy.transactions_used += 1
    policy.amount_reserved_paise += txn.requested_amount_paise
    txn.budget_reserved = True
    _refresh_exhaustion(policy)
    db.flush()


def release(db: Session, policy: AuthorizationPolicy, txn: TransactionRequest) -> None:
    """Hand quota and funds back when a reserved transaction will never pay.

    The transaction slot is returned too: a purchase the user rejected should
    not consume one of their authorized transactions.
    """
    if not txn.budget_reserved:
        return
    policy.amount_reserved_paise = max(
        0, policy.amount_reserved_paise - txn.requested_amount_paise
    )
    policy.transactions_used = max(0, policy.transactions_used - 1)
    txn.budget_reserved = False
    _refresh_exhaustion(policy)
    db.flush()


def settle(db: Session, policy: AuthorizationPolicy, txn: TransactionRequest) -> None:
    """Convert a reservation into real spend once a payment succeeds."""
    if not txn.budget_reserved:
        return
    policy.amount_reserved_paise = max(
        0, policy.amount_reserved_paise - txn.requested_amount_paise
    )
    policy.amount_settled_paise += txn.requested_amount_paise
    txn.budget_reserved = False
    _refresh_exhaustion(policy)
    db.flush()


def _refresh_exhaustion(policy: AuthorizationPolicy) -> None:
    """Keep policy.status honest after any counter change."""
    if policy.status not in (PolicyStatus.ACTIVE, PolicyStatus.EXHAUSTED):
        return

    used_up = policy.transactions_used >= policy.max_transactions
    if policy.one_time_use:
        used_up = used_up or policy.transactions_used >= 1

    policy.status = PolicyStatus.EXHAUSTED if used_up else PolicyStatus.ACTIVE


def expire_stale_policies(db: Session) -> int:
    """Flip ACTIVE policies past their expiry to EXPIRED. Cheap to call often."""
    stale = list(
        db.scalars(
            select(AuthorizationPolicy).where(
                AuthorizationPolicy.status == PolicyStatus.ACTIVE,
                AuthorizationPolicy.expires_at <= utcnow(),
            )
        )
    )
    for policy in stale:
        policy.status = PolicyStatus.EXPIRED
    if stale:
        db.flush()
    return len(stale)
