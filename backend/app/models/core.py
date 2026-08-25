"""All Velora entities.

Money rule: every monetary column is an INTEGER count of **paise** (minor
units), never a float and never rupees. Razorpay speaks paise, floats cannot
represent currency exactly, and mixing the two units is the classic way to
turn 17.99 into 1799. Conversion happens only at the API edge.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id
from app.models.enums import AgentStatus, ApprovalDecision, PolicyStatus, TxnState


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("usr"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    agents: Mapped[list["Agent"]] = relationship(back_populates="user")


class Agent(Base, TimestampMixin):
    """An autonomous actor. Identity is proven by a bearer token whose SHA-256
    hash is stored here; the raw token is shown exactly once, at creation.

    The agent_id in a request body is never trusted. The caller token is
    resolved to an Agent row, and that is the identity the gate evaluates.
    """

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("agt"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(60), nullable=False, default="shopping")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AgentStatus.ACTIVE)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    user: Mapped[User] = relationship(back_populates="agents")


class Product(Base, TimestampMixin):
    """Velora's own catalog.

    The gate resolves price, category and merchant from THIS table using the
    product_id an agent sends. It never accepts those facts from the agent,
    which would let the agent simply declare its way past a category or
    amount rule.
    """

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("prd"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    merchant: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    rating: Mapped[float] = mapped_column(default=0.0)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)


class AuthorizationPolicy(Base, TimestampMixin):
    """The boundary a user draws around an agent.

    Two distinct amount limits, deliberately:
      max_per_transaction_paise - ceiling on any single purchase
      total_budget_paise        - ceiling on the sum of all purchases
    Collapsing these into one max_amount is ambiguous the moment
    max_transactions is greater than 1.

    Counters are authoritative and mutated only under a row lock.
    amount_reserved_paise holds funds committed to transactions that are
    approved-but-unpaid or awaiting human approval, so an agent cannot
    outrun its budget by firing many requests at once.
    """

    __tablename__ = "authorization_policies"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("pol"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), default="Untitled policy")

    max_per_transaction_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_budget_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approval_threshold_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    allowed_categories: Mapped[list[str]] = mapped_column(JSONB, default=list)
    allowed_merchants: Mapped[list[str]] = mapped_column(JSONB, default=list)

    max_transactions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    one_time_use: Mapped[bool] = mapped_column(Boolean, default=False)

    transactions_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amount_reserved_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount_settled_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PolicyStatus.ACTIVE)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def committed_paise(self) -> int:
        """Budget already spoken for: settled payments plus live reservations."""
        return self.amount_settled_paise + self.amount_reserved_paise

    @property
    def remaining_budget_paise(self) -> int:
        return max(0, self.total_budget_paise - self.committed_paise)


class TransactionRequest(Base, TimestampMixin):
    """One purchase attempt and the full record of how it was judged.

    The decision fields are denormalised here on purpose: audit_logs are
    history, not the source of truth for what a transaction is right now.

    policy_snapshot freezes the policy as it read at evaluation time, so an
    audit trail stays reproducible even after the user edits the policy.
    """

    __tablename__ = "transaction_requests"
    __table_args__ = (
        UniqueConstraint("agent_id", "idempotency_key", name="uq_txn_agent_idempotency"),
        Index("ix_txn_state_created", "state", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("txn"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("authorization_policies.id"), nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    merchant: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    requested_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    state: Mapped[str] = mapped_column(String(30), nullable=False, default=TxnState.CREATED)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    agent_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_reserved: Mapped[bool] = mapped_column(Boolean, default=False)

    payment_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRequest(Base, TimestampMixin):
    """A human decision point.

    expires_at is enforced lazily on read and by the sweeper in
    services/expiry.py. A pending approval must never hang forever, because
    silent limbo is a silent failure.
    """

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("apr"))
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transaction_requests.id"), nullable=False, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalDecision.PENDING
    )
    prompt: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(Base, TimestampMixin):
    """Append-only. Never updated, never deleted.

    Each row carries the hash of the previous row for its transaction, so the
    chain is tamper-evident: altering any earlier entry breaks every hash
    after it. seq gives a stable order even within the same millisecond.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        UniqueConstraint("transaction_id", "seq", name="uq_audit_txn_seq"),
        Index("ix_audit_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("aud"))
    transaction_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    policy_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor: Mapped[str] = mapped_column(String(40), nullable=False, default="system")

    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    previous_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
