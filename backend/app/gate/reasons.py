"""Machine-readable reason codes.

Every decision Velora makes resolves to exactly one of these. They are the
stable contract that UI copy, audit logs and agent-facing errors all build
on, so they must never be reworded to change meaning.
"""

from enum import StrEnum


class ReasonCode(StrEnum):
    # Approved
    WITHIN_POLICY = "WITHIN_POLICY"

    # Escalation
    APPROVAL_THRESHOLD_EXCEEDED = "APPROVAL_THRESHOLD_EXCEEDED"

    # Authorization / identity
    NO_AUTHORIZATION = "NO_AUTHORIZATION"
    AUTHORIZATION_INACTIVE = "AUTHORIZATION_INACTIVE"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
    AUTHORIZATION_NOT_YET_VALID = "AUTHORIZATION_NOT_YET_VALID"
    AGENT_SUSPENDED = "AGENT_SUSPENDED"
    AGENT_IDENTITY_MISMATCH = "AGENT_IDENTITY_MISMATCH"

    # Quota
    MAX_TRANSACTIONS_EXCEEDED = "MAX_TRANSACTIONS_EXCEEDED"
    AUTHORIZATION_ALREADY_USED = "AUTHORIZATION_ALREADY_USED"

    # Scope
    MERCHANT_NOT_ALLOWED = "MERCHANT_NOT_ALLOWED"
    CATEGORY_NOT_ALLOWED = "CATEGORY_NOT_ALLOWED"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"

    # Amount
    MAX_AMOUNT_EXCEEDED = "MAX_AMOUNT_EXCEEDED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"

    # Catalog
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    PRODUCT_OUT_OF_STOCK = "PRODUCT_OUT_OF_STOCK"

    # Request handling
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"


#: Codes that describe a hard refusal. Anything here means no payment may
#: ever be created for the transaction.
BLOCKING_CODES = {
    ReasonCode.NO_AUTHORIZATION,
    ReasonCode.AUTHORIZATION_INACTIVE,
    ReasonCode.AUTHORIZATION_EXPIRED,
    ReasonCode.AUTHORIZATION_NOT_YET_VALID,
    ReasonCode.AGENT_SUSPENDED,
    ReasonCode.AGENT_IDENTITY_MISMATCH,
    ReasonCode.MAX_TRANSACTIONS_EXCEEDED,
    ReasonCode.AUTHORIZATION_ALREADY_USED,
    ReasonCode.MERCHANT_NOT_ALLOWED,
    ReasonCode.CATEGORY_NOT_ALLOWED,
    ReasonCode.CURRENCY_MISMATCH,
    ReasonCode.MAX_AMOUNT_EXCEEDED,
    ReasonCode.BUDGET_EXCEEDED,
    ReasonCode.PRODUCT_NOT_FOUND,
    ReasonCode.PRODUCT_OUT_OF_STOCK,
}
