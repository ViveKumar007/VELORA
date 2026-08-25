"""Dashboard aggregates and the live event stream."""

import asyncio
import hmac

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.config import settings
from app.models import (
    ApprovalDecision,
    ApprovalRequest,
    AuthorizationPolicy,
    Decision,
    PolicyStatus,
    TransactionRequest,
    TxnState,
)
from app.schemas.api import DashboardStats
from app.services import events
from app.services.approvals import expire_stale_approvals
from app.services.state_machine import AUTHORIZED_STATES
from app.services.budget import expire_stale_policies
from app.utils.money import format_inr

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(db: DbSession, user: CurrentUser):
    # Sweep first so the numbers shown are not stale by definition.
    expire_stale_policies(db)
    expire_stale_approvals(db)
    db.commit()

    def count_txn(**where) -> int:
        query = select(func.count()).select_from(TransactionRequest).where(
            TransactionRequest.user_id == user.id
        )
        for column, value in where.items():
            query = query.where(getattr(TransactionRequest, column) == value)
        return db.scalar(query) or 0

    def sum_txn(**where) -> int:
        query = select(func.coalesce(func.sum(TransactionRequest.requested_amount_paise), 0)).where(
            TransactionRequest.user_id == user.id
        )
        for column, value in where.items():
            query = query.where(getattr(TransactionRequest, column) == value)
        return db.scalar(query) or 0

    # "In force" means ACTIVE or EXHAUSTED, not ACTIVE alone. A single-use
    # policy flips to EXHAUSTED the moment it reserves budget for a pending
    # approval -- but it is still the boundary governing that agent, and
    # rejecting the purchase returns it to ACTIVE. Counting only ACTIVE would
    # report "no authorizations" precisely while one is doing its job.
    in_force = [PolicyStatus.ACTIVE, PolicyStatus.EXHAUSTED]

    active_authorizations = (
        db.scalar(
            select(func.count())
            .select_from(AuthorizationPolicy)
            .where(
                AuthorizationPolicy.user_id == user.id,
                AuthorizationPolicy.status.in_(in_force),
            )
        )
        or 0
    )

    pending = (
        db.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(
                ApprovalRequest.user_id == user.id,
                ApprovalRequest.decision == ApprovalDecision.PENDING,
            )
        )
        or 0
    )

    total_authorized = (
        db.scalar(
            select(func.coalesce(func.sum(AuthorizationPolicy.total_budget_paise), 0)).where(
                AuthorizationPolicy.user_id == user.id,
                AuthorizationPolicy.status.in_(in_force),
            )
        )
        or 0
    )

    spent = sum_txn(state=TxnState.PAYMENT_SUCCESS)
    blocked_value = sum_txn(decision=Decision.BLOCKED)

    # Counted by state, not by decision: a purchase the gate escalated and the
    # user then approved is an approved purchase, even though the gate's
    # original verdict was PENDING_APPROVAL.
    approved_count = (
        db.scalar(
            select(func.count())
            .select_from(TransactionRequest)
            .where(
                TransactionRequest.user_id == user.id,
                TransactionRequest.state.in_([str(s) for s in AUTHORIZED_STATES]),
            )
        )
        or 0
    )

    return DashboardStats(
        active_authorizations=active_authorizations,
        approved=approved_count,
        blocked=count_txn(state=TxnState.BLOCKED),
        pending_approvals=pending,
        paid=count_txn(state=TxnState.PAYMENT_SUCCESS),
        total_authorized_paise=total_authorized,
        total_spent_paise=spent,
        total_spent_display=format_inr(spent),
        total_blocked_paise=blocked_value,
        total_blocked_display=format_inr(blocked_value),
    )


@router.get("/events")
async def event_stream(request: Request, token: str | None = None):
    """Server-Sent Events.

    Each message says only that something changed; the client refetches. That
    keeps the stream advisory, so a dropped message can never leave the UI
    showing a decision the backend does not agree with.

    The stream carries transaction ids and decisions, so when an operator
    token is configured this endpoint requires it too. EventSource cannot set
    request headers, so it is passed as a query parameter -- acceptable only
    because the alternative is an unauthenticated firehose.
    """
    if settings.operator_token:
        if not token or not hmac.compare_digest(token, settings.operator_token):
            raise HTTPException(status_code=401, detail="Missing or invalid stream token.")

    async def generate():
        queue = events.subscribe()
        try:
            yield 'data: {"event": "connected", "data": {}}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Comment frame: keeps proxies from closing an idle stream.
                    yield ": keep-alive\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
