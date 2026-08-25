"""Authorization policies: the boundary a user draws around an agent."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import (
    Agent,
    AuthorizationPolicy,
    EventType,
    PolicyStatus,
    utcnow,
)
from app.schemas.api import PolicyCreate, PolicyView
from app.services import audit, budget, events
from app.utils.money import format_inr, rupees_to_paise

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.post("", response_model=PolicyView, status_code=201)
def create_policy(payload: PolicyCreate, db: DbSession, user: CurrentUser):
    agent = db.get(Agent, payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="No such agent.")
    if agent.user_id != user.id:
        raise HTTPException(status_code=403, detail="That agent belongs to another user.")

    # Reject policies that cannot mean what the user intended, rather than
    # silently creating a rule that can never fire.
    problem = payload.check_coherence()
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    now = utcnow()
    policy = AuthorizationPolicy(
        user_id=user.id,
        agent_id=agent.id,
        name=payload.name,
        max_per_transaction_paise=rupees_to_paise(payload.max_per_transaction),
        total_budget_paise=rupees_to_paise(payload.total_budget),
        approval_threshold_paise=rupees_to_paise(payload.approval_threshold),
        currency=payload.currency,
        allowed_categories=payload.allowed_categories,
        allowed_merchants=payload.allowed_merchants,
        max_transactions=payload.max_transactions,
        one_time_use=payload.one_time_use,
        valid_from=now,
        expires_at=now + timedelta(minutes=payload.expires_in_minutes),
        status=PolicyStatus.ACTIVE,
    )
    db.add(policy)
    db.flush()

    audit.record(
        db,
        event_type=EventType.STATE_CHANGED,
        agent_id=agent.id,
        policy_id=policy.id,
        actor=user.id,
        explanation=(
            f"Authorization created for {agent.name}: up to "
            f"{format_inr(policy.max_per_transaction_paise)} per purchase, "
            f"{format_inr(policy.total_budget_paise)} in total, auto-approving at or below "
            f"{format_inr(policy.approval_threshold_paise)}."
        ),
        new_state=PolicyStatus.ACTIVE,
        metadata={
            "allowed_categories": policy.allowed_categories,
            "allowed_merchants": policy.allowed_merchants,
            "max_transactions": policy.max_transactions,
            "one_time_use": policy.one_time_use,
            "expires_at": policy.expires_at.isoformat(),
        },
    )
    db.commit()
    events.publish("policy.created", {"policy_id": policy.id, "agent_id": agent.id})
    return PolicyView.build(policy)


@router.get("", response_model=list[PolicyView])
def list_policies(db: DbSession, user: CurrentUser, active_only: bool = False):
    budget.expire_stale_policies(db)
    db.commit()

    query = select(AuthorizationPolicy).where(AuthorizationPolicy.user_id == user.id)
    if active_only:
        query = query.where(AuthorizationPolicy.status == PolicyStatus.ACTIVE)

    policies = db.scalars(query.order_by(AuthorizationPolicy.created_at.desc()))
    return [PolicyView.build(p) for p in policies]


@router.get("/{policy_id}", response_model=PolicyView)
def get_policy(policy_id: str, db: DbSession, user: CurrentUser):
    policy = db.get(AuthorizationPolicy, policy_id)
    if policy is None or policy.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such policy.")
    return PolicyView.build(policy)


@router.post("/{policy_id}/revoke", response_model=PolicyView)
def revoke_policy(policy_id: str, db: DbSession, user: CurrentUser):
    """Withdraw an agent's authority immediately.

    Already-approved transactions keep their reservations; what stops is the
    agent's ability to obtain any new authorization.
    """
    policy = budget.lock_policy(db, policy_id)
    if policy is None or policy.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such policy.")
    if policy.status == PolicyStatus.REVOKED:
        return PolicyView.build(policy)

    previous = policy.status
    policy.status = str(PolicyStatus.REVOKED)
    policy.revoked_at = utcnow()

    audit.record(
        db,
        event_type=EventType.STATE_CHANGED,
        agent_id=policy.agent_id,
        policy_id=policy.id,
        actor=user.id,
        explanation="User revoked this authorization. The agent can no longer transact under it.",
        previous_state=previous,
        new_state=str(PolicyStatus.REVOKED),
    )
    db.commit()
    events.publish("policy.revoked", {"policy_id": policy.id})
    return PolicyView.build(policy)
