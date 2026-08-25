"""Shared request dependencies."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Agent, User
from app.security import hash_token

DbSession = Annotated[Session, Depends(get_db)]


def require_agent(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Agent:
    """Resolve the calling agent from its bearer token.

    This is the identity the gate evaluates. A request body may also carry an
    agent_id, but that is only a claim; check_agent_identity compares it with
    the agent resolved here and blocks any mismatch.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing agent credentials. Send 'Authorization: Bearer <agent token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw = authorization.split(" ", 1)[1].strip()
    agent = db.scalars(select(Agent).where(Agent.token_hash == hash_token(raw))).first()
    if agent is None:
        # No identity resolved, so there is nothing to audit the attempt
        # against. This is the one refusal that stops here.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unrecognised agent token.",
        )

    # A suspended agent is deliberately NOT rejected here. Refusing at the
    # door returned a bare 403 and left no record, which contradicts the whole
    # premise: a suspended agent trying to spend money is exactly the event a
    # trust layer must capture. It now reaches the gate, where
    # check_agent_active blocks it with reason AGENT_SUSPENDED and a full
    # audit trail. (That check was previously unreachable in production.)
    return agent


def _check_operator_token(supplied: str | None) -> None:
    """Gate the human-facing surface behind a shared secret, when configured.

    Approving a purchase and creating a payment are operator actions. If
    OPERATOR_TOKEN is set, they require it. Left unset, the API is
    open, which is only acceptable bound to 127.0.0.1 on a demo machine.
    """
    expected = settings.operator_token
    if not expected:
        return
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid operator token. Send 'X-Velora-Token'.",
        )


def current_user(
    db: DbSession,
    x_user_id: Annotated[str | None, Header()] = None,
    x_velora_token: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the human operator.

    Security note. An earlier version resolved whichever user id arrived in
    the X-User-Id header. Because that header is unauthenticated, anyone who
    knew or guessed a user id could read that user's policies, approve their
    pending purchases and create payments on their behalf -- the per-object
    ownership checks downstream were correct, but they were checking against
    an attacker-chosen identity.

    The header is now ignored unless dev_allow_user_header is explicitly
    switched on for local multi-user testing. By default this is a
    single-operator deployment: the seeded user, optionally behind a shared
    operator token.

    Real per-user sessions are still the right long-term answer, and this
    function is the single place that has to change to add them.
    """
    _check_operator_token(x_velora_token)

    if x_user_id:
        if not settings.dev_allow_user_header:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "X-User-Id is not accepted. Impersonating a user by header is "
                    "disabled; set DEV_ALLOW_USER_HEADER=true for local multi-user "
                    "testing only."
                ),
            )
        user = db.get(User, x_user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"No user {x_user_id}.")
        return user

    user = db.scalars(select(User).order_by(User.created_at.asc()).limit(1)).first()
    if user is None:
        raise HTTPException(
            status_code=503,
            detail="No user exists yet. Run the seed script first: python -m app.seed",
        )
    return user


CurrentAgent = Annotated[Agent, Depends(require_agent)]
CurrentUser = Annotated[User, Depends(current_user)]
