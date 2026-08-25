"""Agent registration.

Creating an agent mints a bearer token that is returned once and never
again -- only its hash is kept. Anyone holding that token can act as the
agent, which is precisely why an agent's authority is bounded by policy
rather than by trust in the token holder.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Agent, AgentStatus, EventType
from app.schemas.api import AgentCreate, AgentCreated, AgentOut
from app.security import generate_agent_token
from app.services import audit

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("", response_model=AgentCreated, status_code=201)
def create_agent(payload: AgentCreate, db: DbSession, user: CurrentUser):
    raw_token, token_hash = generate_agent_token()
    agent = Agent(
        user_id=user.id,
        name=payload.name,
        agent_type=payload.agent_type,
        status=AgentStatus.ACTIVE,
        token_hash=token_hash,
    )
    db.add(agent)
    db.flush()

    audit.record(
        db,
        event_type=EventType.STATE_CHANGED,
        agent_id=agent.id,
        actor=user.id,
        explanation=f"Agent {agent.name} registered. It holds no authority until a policy is created.",
        new_state=AgentStatus.ACTIVE,
    )
    db.commit()

    return AgentCreated(
        id=agent.id,
        name=agent.name,
        agent_type=agent.agent_type,
        status=agent.status,
        created_at=agent.created_at,
        token=raw_token,
    )


@router.get("", response_model=list[AgentOut])
def list_agents(db: DbSession, user: CurrentUser):
    return list(
        db.scalars(
            select(Agent).where(Agent.user_id == user.id).order_by(Agent.created_at.asc())
        )
    )


@router.post("/{agent_id}/suspend", response_model=AgentOut)
def suspend_agent(agent_id: str, db: DbSession, user: CurrentUser):
    """A kill switch that does not depend on any individual policy."""
    agent = db.get(Agent, agent_id)
    if agent is None or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such agent.")

    previous = agent.status
    agent.status = str(AgentStatus.SUSPENDED)
    audit.record(
        db,
        event_type=EventType.STATE_CHANGED,
        agent_id=agent.id,
        actor=user.id,
        explanation=f"User suspended {agent.name}. All further requests will be blocked.",
        previous_state=previous,
        new_state=str(AgentStatus.SUSPENDED),
    )
    db.commit()
    return agent
