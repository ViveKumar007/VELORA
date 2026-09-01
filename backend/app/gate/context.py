"""Inputs and outputs of a policy evaluation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models import Agent, AuthorizationPolicy, CheckStatus, Product
from app.gate.reasons import ReasonCode


def normalize_category(value: str) -> str:
    """Canonical category form: lowercase, underscore-joined.

    The spec's own examples drift between 'electronics', 'Electronics' and
    'Digital Goods'. Without one canonical form, a category check silently
    fails open or closed depending on who typed the policy.
    """
    return "_".join(value.strip().lower().split())


def normalize_merchant(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one rule. Every check produces one of these, including
    the ones that pass, because the decision object has to show the whole
    checklist and not merely the rule that failed."""

    name: str
    status: CheckStatus
    detail: str
    reason_code: ReasonCode | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": str(self.status),
            "detail": self.detail,
            "reason_code": str(self.reason_code) if self.reason_code else None,
        }


@dataclass
class EvalContext:
    """Everything a check is allowed to look at.

    Note what is absent: nothing here comes from the agent except product_id
    and the idempotency key. amount, category and merchant are all read from
    the catalog row, so an agent cannot misdeclare them.
    """

    agent: Agent
    now: datetime
    policy: AuthorizationPolicy | None = None
    product: Product | None = None
    amount_paise: int = 0
    currency: str = "INR"
    category: str = ""
    merchant: str = ""
    claimed_agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    #: Every merchant and category in a multi-item basket.
    #:
    #: A single purchase has one of each, and these stay empty. A basket of
    #: ingredients routinely spans two shops -- rice from Zepto, paneer from
    #: Blinkit -- and the scope checks have to judge all of them, because a
    #: basket is only inside the boundary if every line in it is. Empty means
    #: "fall back to the singular field", so single-purchase behaviour is
    #: byte-for-byte unchanged.
    merchants: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    def all_merchants(self) -> list[str]:
        return self.merchants or ([self.merchant] if self.merchant else [])

    def all_categories(self) -> list[str]:
        return self.categories or ([self.category] if self.category else [])

    @property
    def is_basket(self) -> bool:
        return bool(self.merchants or self.categories)


@dataclass
class Verdict:
    """The full, explainable result of running the gate."""

    decision: str
    reason_code: ReasonCode
    explanation: str
    checks: list[CheckResult]

    def checks_as_dicts(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.checks]
