"""The rules.

Each check is a pure function of an EvalContext that returns exactly one
CheckResult. No check touches the database, performs I/O, or calls a model:
given the same context, a check always returns the same result. That is what
makes authorization deterministic and replayable from an audit record.

Adding a rule means writing a function and appending it to CHECKS. Nothing
else in the engine needs to change.
"""

from collections.abc import Callable

from app.gate.context import (
    CheckResult,
    EvalContext,
    normalize_category,
    normalize_merchant,
)
from app.gate.reasons import ReasonCode
from app.models import AgentStatus, CheckStatus, PolicyStatus
from app.utils.money import format_inr

Check = Callable[[EvalContext], CheckResult]


def _skip(name: str, why: str = "No authorization to evaluate against.") -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.SKIP, detail=why)


def check_authorization_exists(ctx: EvalContext) -> CheckResult:
    name = "Authorization Exists"
    if ctx.policy is None:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            detail="This agent holds no authorization policy, so it has no authority to spend.",
            reason_code=ReasonCode.NO_AUTHORIZATION,
        )
    return CheckResult(name, CheckStatus.PASS, f"Policy {ctx.policy.id} found.")


def check_agent_active(ctx: EvalContext) -> CheckResult:
    name = "Agent Status"
    if ctx.agent.status != AgentStatus.ACTIVE:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            detail=f"Agent {ctx.agent.name} is {ctx.agent.status.lower()} and cannot transact.",
            reason_code=ReasonCode.AGENT_SUSPENDED,
        )
    return CheckResult(name, CheckStatus.PASS, f"Agent {ctx.agent.name} is active.")


def check_agent_identity(ctx: EvalContext) -> CheckResult:
    """The presented token already resolved to ctx.agent. This check catches
    a request whose body claims to act as a different agent, and confirms the
    policy under evaluation actually belongs to the caller."""
    name = "Agent Identity"
    if ctx.claimed_agent_id and ctx.claimed_agent_id != ctx.agent.id:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            detail=(
                f"Request claims agent {ctx.claimed_agent_id} but was signed by "
                f"{ctx.agent.id}."
            ),
            reason_code=ReasonCode.AGENT_IDENTITY_MISMATCH,
        )
    if ctx.policy is not None and ctx.policy.agent_id != ctx.agent.id:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            detail="This policy was issued to a different agent.",
            reason_code=ReasonCode.AGENT_IDENTITY_MISMATCH,
        )
    return CheckResult(name, CheckStatus.PASS, "Token resolves to the authorized agent.")


def check_authorization_active(ctx: EvalContext) -> CheckResult:
    name = "Authorization Active"
    if ctx.policy is None:
        return _skip(name)
    if ctx.policy.status == PolicyStatus.REVOKED:
        return CheckResult(
            name, CheckStatus.FAIL,
            "This authorization was revoked by the user.",
            ReasonCode.AUTHORIZATION_INACTIVE,
        )
    if ctx.policy.status == PolicyStatus.EXHAUSTED:
        # Deliberately not a failure here. EXHAUSTED means "no headroom left",
        # and check_transaction_quota below can say precisely why -- a
        # single-use authorization already spent (AUTHORIZATION_ALREADY_USED)
        # is a different fact from a 5-transaction budget that ran out
        # (MAX_TRANSACTIONS_EXCEEDED). Failing here would flatten both into
        # the single-use wording and mislead the user.
        return CheckResult(
            name, CheckStatus.PASS,
            "Authorization is in force but has no remaining headroom.",
        )
    if ctx.policy.status != PolicyStatus.ACTIVE:
        return CheckResult(
            name, CheckStatus.FAIL,
            f"Authorization status is {ctx.policy.status}.",
            ReasonCode.AUTHORIZATION_INACTIVE,
        )
    return CheckResult(name, CheckStatus.PASS, "Authorization is active.")


def check_validity_window(ctx: EvalContext) -> CheckResult:
    name = "Validity Window"
    if ctx.policy is None:
        return _skip(name)
    if ctx.now < ctx.policy.valid_from:
        return CheckResult(
            name, CheckStatus.FAIL,
            f"Authorization does not begin until {ctx.policy.valid_from:%d %b %Y, %H:%M}.",
            ReasonCode.AUTHORIZATION_NOT_YET_VALID,
        )
    if ctx.now >= ctx.policy.expires_at:
        return CheckResult(
            name, CheckStatus.FAIL,
            f"Authorization expired at {ctx.policy.expires_at:%d %b %Y, %H:%M}.",
            ReasonCode.AUTHORIZATION_EXPIRED,
        )
    return CheckResult(
        name, CheckStatus.PASS,
        f"Valid until {ctx.policy.expires_at:%d %b %Y, %H:%M}.",
    )


def check_product_available(ctx: EvalContext) -> CheckResult:
    name = "Product Resolved"

    # A basket resolves many rows rather than one, and every line was read
    # from the catalog server-side before it got here -- a product id that
    # matched nothing never became a line. So the check is that the basket
    # is non-empty and nothing in it is out of stock.
    if ctx.is_basket:
        basket = (ctx.metadata or {}).get("basket") or {}
        items = basket.get("items") or []
        missing = basket.get("missing_product_ids") or []
        if missing:
            return CheckResult(
                name, CheckStatus.FAIL,
                f"{len(missing)} requested product id(s) match no catalog row.",
                ReasonCode.PRODUCT_NOT_FOUND,
            )
        if not items:
            return CheckResult(
                name, CheckStatus.FAIL,
                "The basket is empty.",
                ReasonCode.PRODUCT_NOT_FOUND,
            )
        return CheckResult(
            name, CheckStatus.PASS,
            f"Resolved {len(items)} catalog items totalling "
            f"{format_inr(basket.get('total_paise', 0))}.",
        )

    if ctx.product is None:
        return CheckResult(
            name, CheckStatus.FAIL,
            "No catalog product matches the requested product_id.",
            ReasonCode.PRODUCT_NOT_FOUND,
        )
    if not ctx.product.in_stock:
        return CheckResult(
            name, CheckStatus.FAIL,
            f"{ctx.product.name} is out of stock.",
            ReasonCode.PRODUCT_OUT_OF_STOCK,
        )
    return CheckResult(
        name, CheckStatus.PASS,
        f"Resolved to {ctx.product.name} at {format_inr(ctx.product.price_paise)}.",
    )


def check_transaction_quota(ctx: EvalContext) -> CheckResult:
    name = "Transaction Quota"
    if ctx.policy is None:
        return _skip(name)
    p = ctx.policy
    if p.one_time_use and p.transactions_used >= 1:
        return CheckResult(
            name, CheckStatus.FAIL,
            "This is a single-use authorization and it has already been used.",
            ReasonCode.AUTHORIZATION_ALREADY_USED,
        )
    if p.transactions_used >= p.max_transactions:
        return CheckResult(
            name, CheckStatus.FAIL,
            f"All {p.max_transactions} authorized transactions have been used.",
            ReasonCode.MAX_TRANSACTIONS_EXCEEDED,
        )
    remaining = p.max_transactions - p.transactions_used
    return CheckResult(name, CheckStatus.PASS, f"{remaining} of {p.max_transactions} remaining.")


def check_merchant(ctx: EvalContext) -> CheckResult:
    """Every merchant involved must be approved.

    A single purchase has exactly one, and this reads as it always did. A
    basket can span several, and the rule there is unanimity rather than
    majority: an authorization that permits Blinkit and Zepto does not permit
    a basket containing one Amazon line, and approving the basket would be
    approving that line. The refusal names the offender rather than the set,
    because "one of your items is not allowed" is not an actionable message.
    """
    name = "Merchant"
    if ctx.policy is None:
        return _skip(name)
    allowed = ctx.policy.allowed_merchants or []
    if not allowed:
        return CheckResult(name, CheckStatus.PASS, "Policy does not restrict merchants.")

    permitted = {normalize_merchant(m) for m in allowed}
    wanted = ctx.all_merchants()
    refused = [m for m in wanted if normalize_merchant(m) not in permitted]

    if refused:
        subject = ", ".join(refused)
        lead = (
            f"{subject} is not an approved merchant."
            if len(refused) == 1
            else f"{subject} are not approved merchants."
        )
        return CheckResult(
            name, CheckStatus.FAIL,
            f"{lead} Allowed: {', '.join(allowed)}.",
            ReasonCode.MERCHANT_NOT_ALLOWED,
        )

    if len(wanted) > 1:
        return CheckResult(
            name, CheckStatus.PASS,
            f"All {len(wanted)} merchants are approved: {', '.join(wanted)}.",
        )
    return CheckResult(name, CheckStatus.PASS, f"{ctx.merchant} is an approved merchant.")


def check_category(ctx: EvalContext) -> CheckResult:
    """Every category involved must be permitted. Unanimity, as above."""
    name = "Category"
    if ctx.policy is None:
        return _skip(name)
    allowed = ctx.policy.allowed_categories or []
    if not allowed:
        return CheckResult(name, CheckStatus.PASS, "Policy does not restrict categories.")

    permitted = {normalize_category(c) for c in allowed}
    wanted = ctx.all_categories()
    refused = [c for c in wanted if normalize_category(c) not in permitted]

    if refused:
        subject = ", ".join(f"'{c}'" for c in refused)
        return CheckResult(
            name, CheckStatus.FAIL,
            (
                f"Category {subject} is outside this authorization, which "
                f"permits only: {', '.join(allowed)}."
            ),
            ReasonCode.CATEGORY_NOT_ALLOWED,
        )

    if len(wanted) > 1:
        return CheckResult(
            name, CheckStatus.PASS,
            f"All {len(wanted)} categories are permitted: {', '.join(wanted)}.",
        )
    return CheckResult(name, CheckStatus.PASS, f"Category '{ctx.category}' is permitted.")


def check_currency(ctx: EvalContext) -> CheckResult:
    name = "Currency"
    if ctx.policy is None:
        return _skip(name)
    if ctx.currency.upper() != ctx.policy.currency.upper():
        return CheckResult(
            name, CheckStatus.FAIL,
            f"Request is in {ctx.currency} but the authorization covers {ctx.policy.currency}.",
            ReasonCode.CURRENCY_MISMATCH,
        )
    return CheckResult(name, CheckStatus.PASS, f"Currency {ctx.currency} matches.")


def check_per_transaction_limit(ctx: EvalContext) -> CheckResult:
    name = "Per-Transaction Limit"
    if ctx.policy is None:
        return _skip(name)
    cap = ctx.policy.max_per_transaction_paise
    if ctx.amount_paise > cap:
        return CheckResult(
            name, CheckStatus.FAIL,
            (
                f"{format_inr(ctx.amount_paise)} exceeds the maximum authorized "
                f"single purchase of {format_inr(cap)}."
            ),
            ReasonCode.MAX_AMOUNT_EXCEEDED,
        )
    return CheckResult(
        name, CheckStatus.PASS,
        f"{format_inr(ctx.amount_paise)} is within the {format_inr(cap)} per-purchase limit.",
    )


def check_total_budget(ctx: EvalContext) -> CheckResult:
    """Budget is measured against settled spend plus live reservations, not
    settled spend alone. Otherwise several pending approvals could each look
    affordable and collectively blow the budget once approved."""
    name = "Remaining Budget"
    if ctx.policy is None:
        return _skip(name)
    p = ctx.policy
    remaining = p.remaining_budget_paise
    if ctx.amount_paise > remaining:
        return CheckResult(
            name, CheckStatus.FAIL,
            (
                f"{format_inr(ctx.amount_paise)} exceeds the {format_inr(remaining)} "
                f"left of a {format_inr(p.total_budget_paise)} budget "
                f"({format_inr(p.amount_settled_paise)} spent, "
                f"{format_inr(p.amount_reserved_paise)} reserved)."
            ),
            ReasonCode.BUDGET_EXCEEDED,
        )
    return CheckResult(
        name, CheckStatus.PASS,
        f"{format_inr(remaining)} of {format_inr(p.total_budget_paise)} remains.",
    )


def check_approval_threshold(ctx: EvalContext) -> CheckResult:
    """The only check that can return REVIEW. Everything above this line is a
    hard yes or no; this one escalates to a human."""
    name = "Approval Threshold"
    if ctx.policy is None:
        return _skip(name)
    threshold = ctx.policy.approval_threshold_paise
    if ctx.amount_paise > threshold:
        return CheckResult(
            name, CheckStatus.REVIEW,
            (
                f"{format_inr(ctx.amount_paise)} exceeds the automatic approval "
                f"threshold of {format_inr(threshold)} and needs your sign-off."
            ),
            ReasonCode.APPROVAL_THRESHOLD_EXCEEDED,
        )
    return CheckResult(
        name, CheckStatus.PASS,
        f"{format_inr(ctx.amount_paise)} is at or below the "
        f"{format_inr(threshold)} auto-approval threshold.",
    )


#: Evaluation order. Every check runs on every request -- the engine does not
#: stop at the first failure, because the decision object must show the whole
#: checklist. Order still matters: it decides which reason_code is reported
#: when more than one rule fails.
CHECKS: list[Check] = [
    check_authorization_exists,
    check_agent_active,
    check_agent_identity,
    check_authorization_active,
    check_validity_window,
    check_product_available,
    check_transaction_quota,
    check_merchant,
    check_category,
    check_currency,
    check_per_transaction_limit,
    check_total_budget,
    check_approval_threshold,
]
