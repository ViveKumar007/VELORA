"""The gate.

evaluate() is a pure function: context in, verdict out. It performs no I/O,
writes nothing, and consults no language model. A model may propose a
purchase and may later narrate a decision in friendlier prose, but it can
never participate in making one -- that is the entire premise of Velora.

Decision precedence, applied after every check has run:

    any FAIL    -> BLOCKED           (no payment may ever be created)
    any REVIEW  -> PENDING_APPROVAL  (a human decides)
    otherwise   -> APPROVED

Running every check rather than stopping at the first failure is deliberate.
The decision object has to show the complete checklist, and a user deserves
to see that three rules failed rather than discovering them one at a time.
"""

from app.gate.checks import CHECKS
from app.gate.context import CheckResult, EvalContext, Verdict
from app.gate.reasons import ReasonCode
from app.models import CheckStatus, Decision
from app.utils.money import format_inr


def evaluate(ctx: EvalContext) -> Verdict:
    """Run every rule against the context and return an explainable verdict."""
    results: list[CheckResult] = [check(ctx) for check in CHECKS]

    failures = [r for r in results if r.status == CheckStatus.FAIL]
    reviews = [r for r in results if r.status == CheckStatus.REVIEW]

    if failures:
        primary = failures[0]
        return Verdict(
            decision=Decision.BLOCKED,
            reason_code=primary.reason_code or ReasonCode.NO_AUTHORIZATION,
            explanation=_blocked_explanation(failures),
            checks=results,
        )

    if reviews:
        primary = reviews[0]
        return Verdict(
            decision=Decision.PENDING_APPROVAL,
            reason_code=primary.reason_code or ReasonCode.APPROVAL_THRESHOLD_EXCEEDED,
            explanation=_pending_explanation(ctx, primary),
            checks=results,
        )

    return Verdict(
        decision=Decision.APPROVED,
        reason_code=ReasonCode.WITHIN_POLICY,
        explanation=_approved_explanation(ctx),
        checks=results,
    )


def _blocked_explanation(failures: list[CheckResult]) -> str:
    if len(failures) == 1:
        return failures[0].detail
    lead = failures[0].detail
    rest = " ".join(f.detail for f in failures[1:])
    return f"{lead} {len(failures) - 1} further rule(s) also failed: {rest}"


def _pending_explanation(ctx: EvalContext, review: CheckResult) -> str:
    if ctx.policy is None:
        return review.detail
    return (
        f"{review.detail} The purchase is within your maximum authorized limit of "
        f"{format_inr(ctx.policy.max_per_transaction_paise)}, so it has been held "
        f"for your approval rather than blocked."
    )


def _approved_explanation(ctx: EvalContext) -> str:
    if ctx.policy is None:
        return "Approved."
    return (
        f"{format_inr(ctx.amount_paise)} for {ctx.product.name if ctx.product else 'this item'} "
        f"is within the {format_inr(ctx.policy.max_per_transaction_paise)} per-purchase limit, "
        f"the merchant and category are both permitted, and the amount is at or below the "
        f"{format_inr(ctx.policy.approval_threshold_paise)} automatic approval threshold."
    )
