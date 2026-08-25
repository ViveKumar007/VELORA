"""Gate tests.

These run without a database on purpose. evaluate() is a pure function, so
the authorization logic can be proven in isolation -- which is exactly the
property that makes it trustworthy.
"""

from datetime import timedelta

import pytest

from app.gate import EvalContext, ReasonCode, evaluate
from app.models import (
    Agent,
    AgentStatus,
    AuthorizationPolicy,
    CheckStatus,
    Decision,
    PolicyStatus,
    Product,
    utcnow,
)
from app.utils.money import format_inr, rupees_to_paise

NOW = utcnow()


def make_agent(status: str = AgentStatus.ACTIVE) -> Agent:
    return Agent(
        id="agt_test",
        user_id="usr_test",
        name="Shopping Agent",
        agent_type="shopping",
        status=status,
        token_hash="x" * 64,
    )


def make_policy(**overrides) -> AuthorizationPolicy:
    defaults = dict(
        id="pol_test",
        user_id="usr_test",
        agent_id="agt_test",
        name="Headphones budget",
        max_per_transaction_paise=rupees_to_paise(2000),
        total_budget_paise=rupees_to_paise(2000),
        approval_threshold_paise=rupees_to_paise(1500),
        currency="INR",
        allowed_categories=["electronics"],
        allowed_merchants=["DemoStore"],
        max_transactions=1,
        one_time_use=True,
        transactions_used=0,
        amount_reserved_paise=0,
        amount_settled_paise=0,
        valid_from=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
        status=PolicyStatus.ACTIVE,
    )
    defaults.update(overrides)
    return AuthorizationPolicy(**defaults)


def make_product(**overrides) -> Product:
    defaults = dict(
        id="prd_test",
        name="SoundBeat Pro",
        description="",
        price_paise=rupees_to_paise(1799),
        currency="INR",
        category="electronics",
        merchant="DemoStore",
        rating=4.6,
        attributes={},
        in_stock=True,
    )
    defaults.update(overrides)
    return Product(**defaults)


def context(product: Product, policy: AuthorizationPolicy | None = None, **kw) -> EvalContext:
    return EvalContext(
        agent=kw.pop("agent", make_agent()),
        now=kw.pop("now", NOW),
        policy=policy if policy is not None else make_policy(),
        product=product,
        amount_paise=product.price_paise,
        currency=product.currency,
        category=product.category,
        merchant=product.merchant,
        **kw,
    )


def status_of(verdict, check_name: str) -> str:
    return next(c.status for c in verdict.checks if c.name == check_name)


# --- The four scenarios from the specification ---------------------------


def test_scenario_1_auto_approval():
    product = make_product(name="SoundBeat Lite", price_paise=rupees_to_paise(1299))
    verdict = evaluate(context(product))

    assert verdict.decision == Decision.APPROVED
    assert verdict.reason_code == ReasonCode.WITHIN_POLICY
    assert all(c.status in (CheckStatus.PASS, CheckStatus.SKIP) for c in verdict.checks)


def test_scenario_2_human_approval_required():
    product = make_product(name="SoundBeat Pro", price_paise=rupees_to_paise(1799))
    verdict = evaluate(context(product))

    assert verdict.decision == Decision.PENDING_APPROVAL
    assert verdict.reason_code == ReasonCode.APPROVAL_THRESHOLD_EXCEEDED
    assert status_of(verdict, "Approval Threshold") == CheckStatus.REVIEW
    # Escalation is not a failure: every hard rule still passed.
    assert status_of(verdict, "Per-Transaction Limit") == CheckStatus.PASS
    assert "1,500" in verdict.explanation


def test_scenario_3_hard_block_on_amount():
    product = make_product(name="Premium Audio Max", price_paise=rupees_to_paise(2499))
    verdict = evaluate(context(product))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.MAX_AMOUNT_EXCEEDED
    assert status_of(verdict, "Per-Transaction Limit") == CheckStatus.FAIL


def test_scenario_4_category_block():
    product = make_product(
        name="Gaming Subscription",
        price_paise=rupees_to_paise(999),
        category="digital_goods",
    )
    verdict = evaluate(context(product))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.CATEGORY_NOT_ALLOWED
    # Cheap enough to auto-approve on price alone -- scope still blocks it.
    assert status_of(verdict, "Per-Transaction Limit") == CheckStatus.PASS


# --- Properties the gate must hold ---------------------------------------


def test_every_check_runs_even_after_a_failure():
    """No early exit: the decision object has to show the whole checklist."""
    product = make_product(price_paise=rupees_to_paise(9999), category="digital_goods")
    verdict = evaluate(context(product))

    assert verdict.decision == Decision.BLOCKED
    failed = {c.name for c in verdict.checks if c.status == CheckStatus.FAIL}
    assert {"Category", "Per-Transaction Limit"} <= failed
    assert len(verdict.checks) == 13


def test_expired_authorization_blocks():
    policy = make_policy(expires_at=NOW - timedelta(minutes=1))
    verdict = evaluate(context(make_product(price_paise=rupees_to_paise(500)), policy))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.AUTHORIZATION_EXPIRED


def test_missing_authorization_blocks():
    ctx = EvalContext(
        agent=make_agent(),
        now=NOW,
        policy=None,
        product=make_product(),
        amount_paise=rupees_to_paise(10),
        currency="INR",
        category="electronics",
        merchant="DemoStore",
    )
    verdict = evaluate(ctx)

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.NO_AUTHORIZATION
    # Policy-dependent rules are skipped, not silently passed.
    assert status_of(verdict, "Category") == CheckStatus.SKIP


def test_currency_mismatch_blocks():
    product = make_product(price_paise=rupees_to_paise(100), currency="USD")
    verdict = evaluate(context(product))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.CURRENCY_MISMATCH


def test_budget_exhausted_blocks_even_when_single_purchase_is_affordable():
    """Per-transaction limit and remaining budget are different rules."""
    policy = make_policy(
        max_transactions=5,
        one_time_use=False,
        total_budget_paise=rupees_to_paise(2000),
        amount_settled_paise=rupees_to_paise(1800),
    )
    product = make_product(price_paise=rupees_to_paise(500))
    verdict = evaluate(context(product, policy))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.BUDGET_EXCEEDED
    assert status_of(verdict, "Per-Transaction Limit") == CheckStatus.PASS


def test_reservations_count_against_budget():
    """A pending approval must consume budget, or several pending requests
    could each look affordable and together exceed it."""
    policy = make_policy(
        max_transactions=5,
        one_time_use=False,
        total_budget_paise=rupees_to_paise(2000),
        amount_reserved_paise=rupees_to_paise(1900),
    )
    verdict = evaluate(context(make_product(price_paise=rupees_to_paise(300)), policy))

    assert verdict.reason_code == ReasonCode.BUDGET_EXCEEDED


def test_one_time_use_policy_rejects_second_purchase():
    policy = make_policy(transactions_used=1)
    verdict = evaluate(context(make_product(price_paise=rupees_to_paise(100)), policy))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.AUTHORIZATION_ALREADY_USED


def test_suspended_agent_blocks():
    ctx = context(make_product(price_paise=rupees_to_paise(100)))
    ctx.agent = make_agent(status=AgentStatus.SUSPENDED)
    verdict = evaluate(ctx)

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.AGENT_SUSPENDED


def test_agent_cannot_act_as_another_agent():
    ctx = context(make_product(price_paise=rupees_to_paise(100)))
    ctx.claimed_agent_id = "agt_someone_else"
    verdict = evaluate(ctx)

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.AGENT_IDENTITY_MISMATCH


def test_out_of_stock_product_blocks():
    verdict = evaluate(context(make_product(in_stock=False)))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.PRODUCT_OUT_OF_STOCK


def test_unresolvable_product_blocks():
    """An agent sending an unknown product_id gets a refusal, not a guess."""
    ctx = context(make_product())
    ctx.product = None
    verdict = evaluate(ctx)

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.PRODUCT_NOT_FOUND


@pytest.mark.parametrize(
    "policy_category,product_category",
    [
        ("Electronics", "electronics"),
        ("electronics", "Electronics"),
        ("Digital Goods", "digital_goods"),
        ("digital goods", "Digital  Goods"),
    ],
)
def test_category_matching_is_normalised(policy_category, product_category):
    """The spec's own examples drift in case and spacing. Without a canonical
    form these comparisons fail open or closed at random."""
    policy = make_policy(allowed_categories=[policy_category])
    product = make_product(price_paise=rupees_to_paise(100), category=product_category)
    verdict = evaluate(context(product, policy))

    assert verdict.decision == Decision.APPROVED


def test_boundary_amounts_are_inclusive():
    """At exactly the threshold: auto-approve. One paisa over: escalate."""
    policy = make_policy(approval_threshold_paise=rupees_to_paise(1500))

    at = evaluate(context(make_product(price_paise=rupees_to_paise(1500)), policy))
    assert at.decision == Decision.APPROVED

    over = evaluate(context(make_product(price_paise=rupees_to_paise(1500) + 1), policy))
    assert over.decision == Decision.PENDING_APPROVAL


def test_evaluation_is_deterministic():
    product = make_product()
    first = evaluate(context(product))
    second = evaluate(context(product))

    assert first.decision == second.decision
    assert first.reason_code == second.reason_code
    assert first.checks_as_dicts() == second.checks_as_dicts()


# --- Money formatting ----------------------------------------------------


@pytest.mark.parametrize(
    "paise,expected",
    [
        (179900, "₹1,799"),
        (129900, "₹1,299"),
        (100, "₹1"),
        (150, "₹1.50"),
        (12345678900, "₹12,34,56,789"),
    ],
)
def test_inr_formatting_uses_indian_grouping(paise, expected):
    assert format_inr(paise) == expected


def test_rupees_to_paise_has_no_float_drift():
    assert rupees_to_paise(1799.99) == 179999
    assert rupees_to_paise("0.1") + rupees_to_paise("0.2") == 30


def test_exhausted_multi_transaction_policy_names_the_transaction_cap():
    """A 5-transaction policy that ran out is not a 'single-use already used'
    situation, and must not report it as one."""
    policy = make_policy(
        max_transactions=5,
        one_time_use=False,
        transactions_used=5,
        total_budget_paise=rupees_to_paise(50000),
        status=PolicyStatus.EXHAUSTED,
    )
    verdict = evaluate(context(make_product(price_paise=rupees_to_paise(100)), policy))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.MAX_TRANSACTIONS_EXCEEDED


def test_exhausted_one_time_policy_still_says_already_used():
    policy = make_policy(one_time_use=True, transactions_used=1, status=PolicyStatus.EXHAUSTED)
    verdict = evaluate(context(make_product(price_paise=rupees_to_paise(100)), policy))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.AUTHORIZATION_ALREADY_USED


def test_revoked_policy_is_still_a_hard_failure():
    """Only EXHAUSTED is delegated to the quota check; REVOKED still fails here."""
    policy = make_policy(status=PolicyStatus.REVOKED)
    verdict = evaluate(context(make_product(price_paise=rupees_to_paise(100)), policy))

    assert verdict.decision == Decision.BLOCKED
    assert verdict.reason_code == ReasonCode.AUTHORIZATION_INACTIVE
