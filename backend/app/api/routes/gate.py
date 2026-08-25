"""The agent-facing endpoints.

Two things an agent can do: ask what to buy (its own reasoning), and ask
permission to buy it (Velora's decision). They are separate endpoints because
they are separate authorities.

Both require the agent's bearer token. Neither can create a payment.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response

from app.agent import recommend
from app.api.deps import CurrentAgent, DbSession
from app.schemas.api import AgentRunIn, AgentRunOut, PurchaseRequestIn, TransactionView
from app.services import events
from app.services.gateway import IdempotencyConflict, handle_purchase_request

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/request", response_model=TransactionView)
def submit_purchase_request(
    payload: PurchaseRequestIn,
    response: Response,
    db: DbSession,
    agent: CurrentAgent,
):
    """An agent asks Velora for permission to buy something.

    The response is always a decision, never a payment. A BLOCKED result is a
    successful API call that returns a refusal -- the agent asked properly and
    was told no.
    """
    try:
        txn, replayed = handle_purchase_request(
            db,
            agent,
            product_id=payload.product_id,
            idempotency_key=payload.idempotency_key,
            claimed_agent_id=payload.agent_id,
            agent_rationale=payload.rationale,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if replayed:
        # Signals a replayed decision rather than a newly made one.
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    else:
        events.publish(
            "transaction.decided",
            {
                "transaction_id": txn.id,
                "decision": txn.decision,
                "state": txn.state,
                "agent_id": txn.agent_id,
            },
        )

    return TransactionView.build(txn, replayed=replayed)


@router.post("/run", response_model=AgentRunOut)
def run_agent(payload: AgentRunIn, db: DbSession, agent: CurrentAgent):
    """Give the agent a goal in plain language and watch it work.

    It reads the goal, ranks the catalog, picks one product, and submits that
    choice to the gate. What comes back may well be a refusal -- the agent
    cannot see the policy it is being judged against.
    """
    recommendation = recommend(db, payload.goal)

    if recommendation.chosen is None or not payload.auto_submit:
        return AgentRunOut(
            goal=payload.goal,
            recommendation=recommendation.to_dict(),
            transaction=None,
        )

    key = payload.idempotency_key or f"run_{uuid.uuid4().hex[:16]}"
    try:
        txn, replayed = handle_purchase_request(
            db,
            agent,
            product_id=recommendation.chosen.product.id,
            idempotency_key=key,
            agent_rationale=recommendation.rationale,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not replayed:
        events.publish(
            "transaction.decided",
            {
                "transaction_id": txn.id,
                "decision": txn.decision,
                "state": txn.state,
                "agent_id": txn.agent_id,
            },
        )

    return AgentRunOut(
        goal=payload.goal,
        recommendation=recommendation.to_dict(),
        transaction=TransactionView.build(txn, replayed=replayed),
    )
