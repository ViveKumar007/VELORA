"""End-to-end flows against a real database.

These are the tests that prove the properties a pure unit test cannot: that
the unique constraint really stops duplicate work, that the row lock really
serialises concurrent requests, and that a blocked transaction really has no
route to a payment through the actual code paths.
"""

import threading

import pytest

from app.models import Decision, PolicyStatus, TxnState
from app.services import audit, budget
from app.services.approvals import ApprovalError, approve, expire_stale_approvals, reject
from app.services.gateway import IdempotencyConflict, handle_purchase_request
from app.services.payments_flow import PaymentNotAllowed, create_payment, handle_webhook_event
from app.services.payments.stub import StubPaymentProvider
from app.utils.money import rupees_to_paise
from tests.conftest import requires_db

pytestmark = requires_db


def submit(db, world, product_key, key="k_00000001", **kw):
    return handle_purchase_request(
        db,
        world["agent"],
        product_id=world["products"][product_key].id,
        idempotency_key=key,
        **kw,
    )


# --- The four decision paths, end to end ---------------------------------


def test_auto_approved_purchase(db, world):
    txn, replayed = submit(db, world, "lite")

    assert not replayed
    assert txn.decision == Decision.APPROVED
    assert txn.state == TxnState.APPROVED
    assert txn.budget_reserved is True

    policy = budget.lock_policy(db, world["policy"].id)
    assert policy.amount_reserved_paise == rupees_to_paise(1299)
    assert policy.transactions_used == 1


def test_escalated_purchase_creates_an_approval(db, world):
    txn, _ = submit(db, world, "pro")

    assert txn.decision == Decision.PENDING_APPROVAL
    assert txn.state == TxnState.PENDING_APPROVAL
    # Budget is held while a human decides.
    assert budget.lock_policy(db, world["policy"].id).amount_reserved_paise == rupees_to_paise(1799)


def test_blocked_on_amount_reserves_nothing(db, world):
    txn, _ = submit(db, world, "premium")

    assert txn.decision == Decision.BLOCKED
    assert txn.reason_code == "MAX_AMOUNT_EXCEEDED"
    assert txn.budget_reserved is False

    policy = budget.lock_policy(db, world["policy"].id)
    assert policy.amount_reserved_paise == 0
    assert policy.transactions_used == 0


def test_blocked_on_category(db, world):
    txn, _ = submit(db, world, "subscription")

    assert txn.decision == Decision.BLOCKED
    assert txn.reason_code == "CATEGORY_NOT_ALLOWED"


# --- The invariant -------------------------------------------------------


def test_a_blocked_transaction_can_never_be_paid(db, world):
    txn, _ = submit(db, world, "premium")
    assert txn.state == TxnState.BLOCKED

    with pytest.raises(PaymentNotAllowed):
        create_payment(db, txn.id)

    db.refresh(txn)
    assert txn.state == TxnState.BLOCKED
    assert txn.payment_order_id is None


def test_a_pending_transaction_cannot_be_paid_before_approval(db, world):
    txn, _ = submit(db, world, "pro")

    with pytest.raises(PaymentNotAllowed):
        create_payment(db, txn.id)


def test_a_rejected_transaction_cannot_be_paid(db, world):
    txn, _ = submit(db, world, "pro")
    reject(db, txn.id, user_id=world["user"].id)

    with pytest.raises(PaymentNotAllowed):
        create_payment(db, txn.id)


# --- Idempotency ---------------------------------------------------------


def test_identical_requests_return_one_transaction(db, world):
    first, replayed_first = submit(db, world, "lite", key="same_key_1")
    second, replayed_second = submit(db, world, "lite", key="same_key_1")

    assert not replayed_first
    assert replayed_second
    assert first.id == second.id

    # Crucially, the second request consumed no additional quota.
    assert budget.lock_policy(db, world["policy"].id).transactions_used == 1


def test_reusing_a_key_for_a_different_product_is_refused(db, world):
    submit(db, world, "lite", key="shared_key_1")

    with pytest.raises(IdempotencyConflict):
        submit(db, world, "pro", key="shared_key_1")


def test_duplicate_suppression_is_audited(db, world):
    txn, _ = submit(db, world, "lite", key="audited_key_1")
    submit(db, world, "lite", key="audited_key_1")

    events = [e.event_type for e in audit.trail(db, txn.id)]
    assert "DUPLICATE_SUPPRESSED" in events


# --- Concurrency ---------------------------------------------------------


def test_concurrent_requests_cannot_both_consume_a_one_time_authorization(engine, world):
    """Two requests race for a single-use policy. Exactly one may win."""
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []

    def worker(key: str):
        session = Session()
        try:
            agent = session.get(type(world["agent"]), world["agent"].id)
            barrier.wait(timeout=10)
            txn, _ = handle_purchase_request(
                session,
                agent,
                product_id=world["products"]["lite"].id,
                idempotency_key=key,
            )
            results.append(txn.decision)
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=(f"race_key_{i}",)) for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"Unexpected errors: {errors}"
    assert sorted(results) == ["APPROVED", "BLOCKED"], (
        f"A single-use authorization was consumed twice: {results}"
    )


# --- Approval flow -------------------------------------------------------


def test_approve_then_pay_then_settle(db, world):
    txn, _ = submit(db, world, "pro")
    approve(db, txn.id, user_id=world["user"].id)
    assert txn.state == TxnState.APPROVED

    txn = create_payment(db, txn.id)
    assert txn.state == TxnState.PAYMENT_CREATED
    assert txn.payment_order_id

    event = StubPaymentProvider.capture_payload(txn.payment_order_id, succeeded=True)
    handle_webhook_event(db, event)

    db.refresh(txn)
    assert txn.state == TxnState.PAYMENT_SUCCESS

    policy = budget.lock_policy(db, world["policy"].id)
    assert policy.amount_settled_paise == rupees_to_paise(1799)
    assert policy.amount_reserved_paise == 0
    assert policy.status == PolicyStatus.EXHAUSTED


def test_rejecting_returns_the_budget_and_the_transaction_slot(db, world):
    txn, _ = submit(db, world, "pro")
    reject(db, txn.id, user_id=world["user"].id)

    db.refresh(txn)
    assert txn.state == TxnState.REJECTED

    policy = budget.lock_policy(db, world["policy"].id)
    assert policy.amount_reserved_paise == 0
    assert policy.transactions_used == 0
    assert policy.status == PolicyStatus.ACTIVE


def test_approving_twice_is_refused(db, world):
    txn, _ = submit(db, world, "pro")
    approve(db, txn.id, user_id=world["user"].id)

    with pytest.raises(ApprovalError):
        approve(db, txn.id, user_id=world["user"].id)


def test_expired_approval_cannot_be_approved(db, world):
    from datetime import timedelta

    from app.models import ApprovalRequest, utcnow
    from sqlalchemy import select

    txn, _ = submit(db, world, "pro")
    approval = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.transaction_id == txn.id)
    ).first()
    approval.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(ApprovalError):
        approve(db, txn.id, user_id=world["user"].id)

    db.refresh(txn)
    assert txn.state == TxnState.EXPIRED
    assert budget.lock_policy(db, world["policy"].id).amount_reserved_paise == 0


def test_sweeper_expires_stale_approvals(db, world):
    from datetime import timedelta

    from app.models import ApprovalRequest, utcnow
    from sqlalchemy import select

    txn, _ = submit(db, world, "pro")
    approval = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.transaction_id == txn.id)
    ).first()
    approval.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    assert expire_stale_approvals(db) == 1
    db.refresh(txn)
    assert txn.state == TxnState.EXPIRED


# --- Payment failures ----------------------------------------------------


def test_provider_failure_is_distinct_from_authorization_failure(db, world):
    txn, _ = submit(db, world, "lite")
    txn = create_payment(db, txn.id, force_failure=True)

    assert txn.state == TxnState.PAYMENT_CREATION_FAILED
    assert txn.decision == Decision.APPROVED  # authorization still succeeded
    assert txn.payment_error

    trail = " ".join(e.explanation for e in audit.trail(db, txn.id))
    assert "Authorization was successful" in trail

    # Retryable: the budget is still held.
    assert budget.lock_policy(db, world["policy"].id).amount_reserved_paise > 0


def test_failed_payment_releases_the_budget(db, world):
    txn, _ = submit(db, world, "lite")
    txn = create_payment(db, txn.id)

    handle_webhook_event(
        db, StubPaymentProvider.capture_payload(txn.payment_order_id, succeeded=False)
    )

    db.refresh(txn)
    assert txn.state == TxnState.PAYMENT_FAILED
    policy = budget.lock_policy(db, world["policy"].id)
    assert policy.amount_reserved_paise == 0
    assert policy.amount_settled_paise == 0


def test_duplicate_webhook_is_ignored(db, world):
    txn, _ = submit(db, world, "lite")
    txn = create_payment(db, txn.id)
    event = StubPaymentProvider.capture_payload(txn.payment_order_id, succeeded=True)

    handle_webhook_event(db, event)
    handle_webhook_event(db, event)

    db.refresh(txn)
    assert txn.state == TxnState.PAYMENT_SUCCESS
    policy = budget.lock_policy(db, world["policy"].id)
    # Settled exactly once.
    assert policy.amount_settled_paise == rupees_to_paise(1299)


def test_creating_a_payment_twice_returns_the_same_order(db, world):
    txn, _ = submit(db, world, "lite")
    first = create_payment(db, txn.id)
    order_id = first.payment_order_id
    second = create_payment(db, txn.id)

    assert second.payment_order_id == order_id


# --- Audit ---------------------------------------------------------------


def test_audit_chain_verifies(db, world):
    txn, _ = submit(db, world, "pro")
    approve(db, txn.id, user_id=world["user"].id)
    create_payment(db, txn.id)

    result = audit.verify_chain(db, txn.id)
    assert result["valid"] is True
    assert result["entries"] > 5


def test_tampering_with_the_audit_trail_is_detected(db, world):
    txn, _ = submit(db, world, "premium")
    entries = audit.trail(db, txn.id)

    victim = entries[len(entries) // 2]
    victim.explanation = "Everything was fine, honestly."
    db.commit()

    result = audit.verify_chain(db, txn.id)
    assert result["valid"] is False
    assert result["broken_at_seq"] == victim.seq


def test_policy_snapshot_survives_a_later_policy_edit(db, world):
    txn, _ = submit(db, world, "premium")
    original_limit = txn.policy_snapshot["max_per_transaction_paise"]

    policy = budget.lock_policy(db, world["policy"].id)
    policy.max_per_transaction_paise = rupees_to_paise(9999)
    db.commit()

    db.refresh(txn)
    assert txn.policy_snapshot["max_per_transaction_paise"] == original_limit
    assert txn.reason_code == "MAX_AMOUNT_EXCEEDED"


def test_exhausted_policy_gives_a_precise_reason_not_no_authorization(db, world):
    """Once a one-time authorization is used, the next request must say so.

    Reporting NO_AUTHORIZATION here would be actively misleading: the agent
    was granted authority, it simply spent it.
    """
    first, _ = submit(db, world, "lite", key="exhaust_1")
    approve_needed = first.state == TxnState.PENDING_APPROVAL
    if approve_needed:
        approve(db, first.id, user_id=world["user"].id)

    second, _ = submit(db, world, "lite", key="exhaust_2")

    assert second.decision == Decision.BLOCKED
    assert second.reason_code == "AUTHORIZATION_ALREADY_USED"
    assert "NO_AUTHORIZATION" != second.reason_code


def test_agent_with_no_policy_at_all_gets_no_authorization(db, world):
    """The reserved meaning of NO_AUTHORIZATION: never granted anything."""
    from app.models import Agent, AgentStatus
    from app.security import generate_agent_token

    raw, token_hash = generate_agent_token()
    stranger = Agent(
        user_id=world["user"].id,
        name="Unauthorized Agent",
        agent_type="shopping",
        status=AgentStatus.ACTIVE,
        token_hash=token_hash,
    )
    db.add(stranger)
    db.commit()

    txn, _ = handle_purchase_request(
        db,
        stranger,
        product_id=world["products"]["lite"].id,
        idempotency_key="stranger_key_1",
    )

    assert txn.decision == Decision.BLOCKED
    assert txn.reason_code == "NO_AUTHORIZATION"


def test_revoked_policy_reports_inactive(db, world):
    from app.models import PolicyStatus as PS

    policy = budget.lock_policy(db, world["policy"].id)
    policy.status = str(PS.REVOKED)
    db.commit()

    txn, _ = submit(db, world, "lite", key="revoked_key_1")

    assert txn.decision == Decision.BLOCKED
    assert txn.reason_code == "AUTHORIZATION_INACTIVE"


def test_concurrent_duplicate_requests_do_not_collide_on_audit_seq(engine, world):
    """Regression: audit.record computed seq with MAX(seq)+1 and no lock, so
    two duplicate requests hitting the same transaction both produced the same
    seq and one died on uq_audit_txn_seq -- a 500 for the caller."""
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(4)
    errors: list = []
    ids: list = []

    # Seed the transaction once so every thread takes the duplicate path.
    seed_session = Session()
    agent = seed_session.get(type(world["agent"]), world["agent"].id)
    first, _ = handle_purchase_request(
        seed_session, agent,
        product_id=world["products"]["lite"].id,
        idempotency_key="audit_race_key",
    )
    seed_session.close()

    def worker():
        session = Session()
        try:
            local_agent = session.get(type(world["agent"]), world["agent"].id)
            barrier.wait(timeout=10)
            txn, _ = handle_purchase_request(
                session, local_agent,
                product_id=world["products"]["lite"].id,
                idempotency_key="audit_race_key",
            )
            ids.append(txn.id)
        except Exception as exc:  # noqa: BLE001 - asserted below
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25)

    assert not errors, f"Concurrent duplicates raised: {errors}"
    assert set(ids) == {first.id}, f"Duplicate created a second transaction: {ids}"

    verify_session = Session()
    try:
        result = audit.verify_chain(verify_session, first.id)
        assert result["valid"], f"Audit chain broken by concurrency: {result}"
        seqs = [e.seq for e in audit.trail(verify_session, first.id)]
        assert seqs == sorted(set(seqs)), f"seq values not unique/ordered: {seqs}"
    finally:
        verify_session.close()
