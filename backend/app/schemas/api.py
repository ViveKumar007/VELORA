"""Request and response shapes.

Rupees in, rupees out. Paise never leave the backend unlabelled: every
monetary field is either suffixed _paise or accompanied by a _display string,
so no consumer has to guess which unit it holds.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.utils.money import format_inr, paise_to_rupees


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ----------------------------------------------------------------


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORMModel):
    id: str
    name: str
    email: str
    created_at: datetime


class UserSession(BaseModel):
    token: str
    user: "UserOut"


class MerchantSession(BaseModel):
    token: str
    merchant: "MerchantSelf"


# --- Users & agents ------------------------------------------------------


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agent_type: str = "shopping"


class AgentOut(ORMModel):
    id: str
    name: str
    agent_type: str
    status: str
    created_at: datetime


class AgentCreated(AgentOut):
    token: str = Field(description="Shown once. Store it now; it cannot be retrieved again.")


# --- Products ------------------------------------------------------------


class ProductOut(ORMModel):
    id: str
    name: str
    description: str
    price_paise: int
    currency: str
    category: str
    merchant: str
    rating: float
    attributes: dict[str, Any]
    in_stock: bool

    @computed_field
    @property
    def price_display(self) -> str:
        return format_inr(self.price_paise)


# --- Merchants -----------------------------------------------------------


class MerchantOut(ORMModel):
    id: str
    slug: str
    name: str
    description: str
    categories: list[str]
    agent_ready: bool
    status: str


class MerchantSelf(MerchantOut):
    """A merchant's view of themselves.

    Separate from MerchantOut because that one is public -- it appears in the
    agent catalog and the public profile, and a seller's contact email is not
    something to publish to every anonymous caller.
    """

    email: str | None = None


class MerchantStats(BaseModel):
    """A merchant's view: what agent traffic did for their revenue."""

    merchant: MerchantSelf
    products: int
    paid: int
    revenue_paise: int
    revenue_display: str
    blocked: int
    recovery_offered: int = Field(
        description="Blocked purchases where an in-policy alternative was offered."
    )


class AgentCatalog(BaseModel):
    """A storefront in a form an autonomous buyer can consume.

    Includes the purchase protocol on purpose: an agent should not have to
    reverse-engineer how to transact, and should know before it starts that
    purchases are gated and may be refused.
    """

    version: str
    currency: str
    amount_unit: str
    merchants: list[MerchantOut]
    items: list[dict[str, Any]]
    purchase_protocol: dict[str, Any]


# --- Policies ------------------------------------------------------------


class PolicyCreate(BaseModel):
    """Amounts are given in rupees; Velora stores paise."""

    agent_id: str
    name: str = "Untitled policy"
    max_per_transaction: float = Field(gt=0, description="Ceiling for any single purchase.")
    total_budget: float = Field(gt=0, description="Ceiling for all purchases combined.")
    approval_threshold: float = Field(
        ge=0, description="At or below this, Velora approves automatically."
    )
    currency: str = "INR"
    allowed_categories: list[str] = Field(default_factory=list)
    allowed_merchants: list[str] = Field(default_factory=list)
    max_transactions: int = Field(default=1, ge=1)
    one_time_use: bool = False
    expires_in_minutes: int = Field(default=30, ge=1)

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    def check_coherence(self) -> str | None:
        """Catch policies that cannot mean what the user intended."""
        if self.approval_threshold > self.max_per_transaction:
            return (
                "The auto-approval threshold is above the per-transaction limit, so "
                "nothing would ever need approval. Lower the threshold or raise the limit."
            )
        if self.total_budget < self.max_per_transaction:
            return (
                "The total budget is smaller than the per-transaction limit, so the "
                "per-transaction limit could never be reached."
            )
        return None


class PolicyOut(ORMModel):
    id: str
    agent_id: str
    name: str
    max_per_transaction_paise: int
    total_budget_paise: int
    approval_threshold_paise: int
    currency: str
    allowed_categories: list[str]
    allowed_merchants: list[str]
    max_transactions: int
    one_time_use: bool
    transactions_used: int
    amount_reserved_paise: int
    amount_settled_paise: int
    valid_from: datetime
    expires_at: datetime
    status: str
    created_at: datetime


class PolicyView(BaseModel):
    """PolicyOut plus the derived numbers a dashboard actually renders."""

    policy: PolicyOut
    remaining_budget_paise: int
    remaining_budget_display: str
    max_per_transaction_display: str
    total_budget_display: str
    approval_threshold_display: str
    transactions_remaining: int

    @classmethod
    def build(cls, policy) -> "PolicyView":
        return cls(
            policy=PolicyOut.model_validate(policy),
            remaining_budget_paise=policy.remaining_budget_paise,
            remaining_budget_display=format_inr(policy.remaining_budget_paise),
            max_per_transaction_display=format_inr(policy.max_per_transaction_paise),
            total_budget_display=format_inr(policy.total_budget_paise),
            approval_threshold_display=format_inr(policy.approval_threshold_paise),
            transactions_remaining=max(
                0, policy.max_transactions - policy.transactions_used
            ),
        )


# --- Agent requests ------------------------------------------------------


class PurchaseRequestIn(BaseModel):
    """What an agent is allowed to ask for.

    Note the absence of amount, category and merchant. Velora reads those
    from its own catalog, so there is no field in which an agent could
    misdeclare a purchase to slip past a rule.
    """

    product_id: str
    idempotency_key: str = Field(min_length=8, max_length=120)
    agent_id: str | None = Field(
        default=None,
        description="Optional self-declared id. Verified against the bearer token.",
    )
    rationale: str | None = None


class CheckOut(BaseModel):
    name: str
    status: str
    detail: str
    reason_code: str | None = None


class TransactionOut(ORMModel):
    id: str
    agent_id: str
    policy_id: str | None
    product_id: str | None
    product_name: str
    merchant: str
    category: str
    requested_amount_paise: int
    currency: str
    state: str
    decision: str | None
    reason_code: str | None
    explanation: str | None
    checks: list[CheckOut]
    agent_rationale: str | None
    recovery: dict[str, Any] | None = None
    payment_order_id: str | None
    payment_id: str | None
    payment_error: str | None
    created_at: datetime
    decided_at: datetime | None


class TransactionView(BaseModel):
    transaction: TransactionOut
    amount_display: str
    replayed: bool = False

    @classmethod
    def build(cls, txn, replayed: bool = False) -> "TransactionView":
        return cls(
            transaction=TransactionOut.model_validate(txn),
            amount_display=format_inr(txn.requested_amount_paise),
            replayed=replayed,
        )


# --- Approvals -----------------------------------------------------------


class ApprovalOut(BaseModel):
    id: str
    transaction_id: str
    decision: str
    prompt: str
    expires_at: datetime
    created_at: datetime
    transaction: TransactionOut
    amount_display: str


class RejectIn(BaseModel):
    note: str | None = None


# --- Audit ---------------------------------------------------------------


class AuditEntryOut(ORMModel):
    id: str
    seq: int
    transaction_id: str | None
    agent_id: str | None
    policy_id: str | None
    actor: str
    event_type: str
    decision: str | None
    reason_code: str | None
    explanation: str
    previous_state: str | None
    new_state: str | None
    event_metadata: dict[str, Any]
    entry_hash: str
    prev_hash: str | None
    created_at: datetime


class AuditTrailOut(BaseModel):
    transaction_id: str
    entries: list[AuditEntryOut]
    integrity: dict[str, Any]


# --- Agent console -------------------------------------------------------


class AgentRunIn(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    idempotency_key: str | None = None
    auto_submit: bool = Field(
        default=True,
        description="If false, return the recommendation without asking the gate.",
    )


class AgentRunOut(BaseModel):
    goal: str
    recommendation: dict[str, Any]
    transaction: TransactionView | None = None


# --- Payments ------------------------------------------------------------


class PaymentCreateIn(BaseModel):
    force_failure: bool = Field(
        default=False,
        description="Demo aid: make the provider fail so the failure path can be shown.",
    )


class SimulatePaymentIn(BaseModel):
    transaction_id: str
    succeed: bool = True


class PaymentConfirmIn(BaseModel):
    """The result Razorpay Checkout hands back to the browser.

    Untrusted until the signature verifies server-side.
    """

    razorpay_payment_id: str = Field(min_length=4, max_length=120)
    razorpay_signature: str = Field(min_length=16, max_length=256)


class PublicConfig(BaseModel):
    """Non-secret settings the frontend needs at runtime.

    razorpay_key_id is the publishable half of the key pair and is designed to
    be visible in the browser. The key SECRET never leaves the server.
    """

    payment_provider: str
    razorpay_key_id: str = ""
    payment_methods: dict[str, bool] | None = Field(
        default=None,
        description="Methods the account can accept. None means 'show everything'.",
    )


# --- Dashboard -----------------------------------------------------------


class DashboardStats(BaseModel):
    active_authorizations: int
    approved: int
    blocked: int
    pending_approvals: int
    paid: int
    total_authorized_paise: int
    total_spent_paise: int
    total_spent_display: str
    total_blocked_paise: int
    total_blocked_display: str


def rupees(paise: int) -> float:
    return paise_to_rupees(paise)
