"""Security regression tests.

Each of these pins a hole that was found by probing the running system, so
that closing it stays closed.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def client(db, world, monkeypatch):
    """A TestClient wired to the test database, signed in as the buyer.

    Authenticated by default because that is the ordinary case. Tests that
    need to probe the unauthenticated path override the Authorization header
    explicitly, so the intent is visible at the call site.
    """
    from app.api.deps import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, headers=world["auth"])
    app.dependency_overrides.clear()


# --- Impersonation via X-User-Id ----------------------------------------


def test_x_user_id_header_cannot_impersonate_a_user(client, world):
    """Regression: current_user resolved whatever user id arrived in the
    X-User-Id header. Anyone who guessed a user id could read that user's
    policies, approve their purchases and create payments for them."""
    victim = world["user"].id

    for method, path in [
        ("GET", "/api/policies"),
        ("GET", "/api/agents"),
        ("GET", "/api/dashboard"),
        ("GET", "/api/approvals"),
    ]:
        response = client.request(method, path, headers={"X-User-Id": victim})
        assert response.status_code == 403, f"{method} {path} accepted impersonation"
        assert "not accepted" in response.json()["detail"]


def test_impersonation_cannot_approve_or_pay(client, world):
    # Create the pending purchase through the agent API, as an agent would.
    response = client.post(
        "/api/agent/request",
        json={"product_id": world["products"]["pro"].id, "idempotency_key": "sec_key_00001"},
        headers={"Authorization": f"Bearer {world['token']}"},
    )
    assert response.status_code == 200
    txn_id = response.json()["transaction"]["id"]
    assert response.json()["transaction"]["state"] == "PENDING_APPROVAL"

    victim = world["user"].id
    blocked = client.post(
        f"/api/transactions/{txn_id}/approve", json={}, headers={"X-User-Id": victim}
    )
    assert blocked.status_code == 403

    blocked_pay = client.post(
        f"/api/transactions/{txn_id}/payment",
        json={"force_failure": False},
        headers={"X-User-Id": victim},
    )
    assert blocked_pay.status_code == 403

    # And the purchase is untouched.
    current = client.get(f"/api/transactions/{txn_id}")
    assert current.json()["transaction"]["state"] == "PENDING_APPROVAL"


def test_operator_actions_still_work_without_the_header(client, world):
    assert client.get("/api/policies").status_code == 200
    assert client.get("/api/dashboard").status_code == 200


# --- Operator token ------------------------------------------------------


def test_operator_token_is_enforced_when_configured(client, world, monkeypatch):
    monkeypatch.setattr(settings, "operator_token", "s3cret")

    assert client.get("/api/policies").status_code == 401
    assert client.get("/api/policies", headers={"X-Velora-Token": "wrong"}).status_code == 401
    assert client.get("/api/policies", headers={"X-Velora-Token": "s3cret"}).status_code == 200

    # Health stays public so a load balancer can probe it.
    assert client.get("/api/health").status_code == 200


def test_event_stream_requires_the_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    assert client.get("/api/events").status_code == 401
    assert client.get("/api/events?token=wrong").status_code == 401


# --- Webhook forgery -----------------------------------------------------


def test_stub_mode_refuses_external_webhooks(client, world):
    """The stub's signing secret is in the source tree, so a correctly signed
    webhook proves nothing. In stub mode the public endpoint is closed."""
    from app.services.payments.stub import StubPaymentProvider

    payload = json.dumps(
        StubPaymentProvider.capture_payload("order_stub_forged", succeeded=True)
    ).encode()

    response = client.post(
        "/api/webhooks/payment",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Velora-Signature": StubPaymentProvider.sign(payload),
        },
    )
    assert response.status_code == 404
    assert "does not accept external webhooks" in response.json()["detail"]


# --- Agent identity ------------------------------------------------------


def test_agent_token_is_required(client, world):
    response = client.post(
        "/api/agent/request",
        json={"product_id": world["products"]["lite"].id, "idempotency_key": "sec_noauth_1"},
        headers={"Authorization": ""},   # explicitly strip the buyer session
    )
    assert response.status_code == 401


def test_invalid_agent_token_is_rejected(client, world):
    response = client.post(
        "/api/agent/request",
        json={"product_id": world["products"]["lite"].id, "idempotency_key": "sec_badtok_1"},
        headers={"Authorization": "Bearer vla_not_a_real_token"},
    )
    assert response.status_code == 401


def test_agent_cannot_claim_another_identity(client, world):
    response = client.post(
        "/api/agent/request",
        json={
            "product_id": world["products"]["lite"].id,
            "idempotency_key": "sec_spoof_001",
            "agent_id": "agt_someone_else",
        },
        headers={"Authorization": f"Bearer {world['token']}"},
    )
    assert response.status_code == 200
    body = response.json()["transaction"]
    assert body["decision"] == "BLOCKED"
    assert body["reason_code"] == "AGENT_IDENTITY_MISMATCH"


# --- No payment path outside the gate ------------------------------------


def test_no_route_creates_a_payment_without_authorization(client, world):
    """Structural: the only endpoint that reaches the payment provider is
    /api/transactions/{id}/payment, and it refuses anything not authorized."""
    response = client.post(
        "/api/agent/request",
        json={"product_id": world["products"]["premium"].id, "idempotency_key": "sec_blocked_1"},
        headers={"Authorization": f"Bearer {world['token']}"},
    )
    txn = response.json()["transaction"]
    assert txn["decision"] == "BLOCKED"

    refused = client.post(
        f"/api/transactions/{txn['id']}/payment", json={"force_failure": False}
    )
    assert refused.status_code == 409

    current = client.get(f"/api/transactions/{txn['id']}").json()["transaction"]
    assert current["state"] == "BLOCKED"
    assert current["payment_order_id"] is None


def test_suspended_agent_is_blocked_with_an_audit_trail(client, world, db):
    """Regression: require_agent returned a bare 403 for suspended agents, so
    the attempt left no record and gate.check_agent_active was unreachable."""
    from app.models import AgentStatus
    from app.services import audit

    agent = db.get(type(world["agent"]), world["agent"].id)
    agent.status = str(AgentStatus.SUSPENDED)
    db.commit()

    response = client.post(
        "/api/agent/request",
        json={"product_id": world["products"]["lite"].id, "idempotency_key": "sec_susp_0001"},
        headers={"Authorization": f"Bearer {world['token']}"},
    )

    assert response.status_code == 200, "suspended agent should get a decision, not a bare error"
    txn = response.json()["transaction"]
    assert txn["decision"] == "BLOCKED"
    assert txn["reason_code"] == "AGENT_SUSPENDED"
    assert txn["state"] == "BLOCKED"

    trail = audit.trail(db, txn["id"])
    assert trail, "the refusal must be auditable"
    assert any(e.reason_code == "AGENT_SUSPENDED" for e in trail)


def test_sql_injection_in_filters_is_parameterised(client, world):
    for payload in ["' OR '1'='1", "'; DROP TABLE transaction_requests; --", "%' --"]:
        response = client.get("/api/transactions", params={"state": payload})
        assert response.status_code == 200
        assert response.json() == []

    # The table is still there.
    assert client.get("/api/transactions").status_code == 200


# --- Client-side payment confirmation ------------------------------------


def _approved_order(client, world, key):
    """Drive a transaction to PAYMENT_CREATED and return (txn_id, order_id)."""
    response = client.post(
        "/api/agent/request",
        json={"product_id": world["products"]["lite"].id, "idempotency_key": key},
        headers={"Authorization": f"Bearer {world['token']}"},
    )
    txn_id = response.json()["transaction"]["id"]
    paid = client.post(f"/api/transactions/{txn_id}/payment", json={"force_failure": False})
    return txn_id, paid.json()["transaction"]["payment_order_id"]


def test_forged_payment_confirmation_is_refused(client, world, db):
    """The browser says 'I paid'. Without a valid signature that means nothing."""
    from app.services import audit

    txn_id, _ = _approved_order(client, world, "confirm_forge_1")

    response = client.post(
        f"/api/transactions/{txn_id}/payment/confirm",
        json={
            "razorpay_payment_id": "pay_totally_made_up",
            "razorpay_signature": "0" * 64,
        },
    )
    assert response.status_code == 409
    assert "signature" in response.json()["detail"].lower()

    current = client.get(f"/api/transactions/{txn_id}").json()["transaction"]
    assert current["state"] == "PAYMENT_CREATED", "a forged confirmation must not settle"

    # The rejection is recorded, not silently dropped.
    trail = audit.trail(db, txn_id)
    assert any("signature did not verify" in e.explanation for e in trail)


def test_valid_payment_confirmation_settles(client, world, db):
    from app.services import budget
    from app.services.payments.stub import StubPaymentProvider
    from app.utils.money import rupees_to_paise

    txn_id, order_id = _approved_order(client, world, "confirm_valid_1")
    payment_id = "pay_stub_valid_0001"

    response = client.post(
        f"/api/transactions/{txn_id}/payment/confirm",
        json={
            "razorpay_payment_id": payment_id,
            "razorpay_signature": StubPaymentProvider.sign_payment(order_id, payment_id),
        },
    )
    assert response.status_code == 200
    assert response.json()["transaction"]["state"] == "PAYMENT_SUCCESS"
    assert response.json()["transaction"]["payment_id"] == payment_id

    # Settled through the same accounting path as a webhook.
    policy = budget.lock_policy(db, world["policy"].id)
    assert policy.amount_settled_paise == rupees_to_paise(1299)
    assert policy.amount_reserved_paise == 0


def test_confirmation_is_idempotent(client, world, db):
    """Double-submitting the confirm call must not settle twice."""
    from app.services import budget
    from app.services.payments.stub import StubPaymentProvider
    from app.utils.money import rupees_to_paise

    txn_id, order_id = _approved_order(client, world, "confirm_twice_1")
    payment_id = "pay_stub_twice_0001"
    body = {
        "razorpay_payment_id": payment_id,
        "razorpay_signature": StubPaymentProvider.sign_payment(order_id, payment_id),
    }

    first = client.post(f"/api/transactions/{txn_id}/payment/confirm", json=body)
    second = client.post(f"/api/transactions/{txn_id}/payment/confirm", json=body)

    assert first.json()["transaction"]["state"] == "PAYMENT_SUCCESS"
    assert second.json()["transaction"]["state"] == "PAYMENT_SUCCESS"

    policy = budget.lock_policy(db, world["policy"].id)
    assert policy.amount_settled_paise == rupees_to_paise(1299), "settled twice"


def test_confirmation_cannot_settle_an_unpaid_transaction(client, world):
    """A blocked transaction has no order, so there is nothing to confirm."""
    response = client.post(
        "/api/agent/request",
        json={"product_id": world["products"]["premium"].id, "idempotency_key": "confirm_blk_1"},
        headers={"Authorization": f"Bearer {world['token']}"},
    )
    txn_id = response.json()["transaction"]["id"]

    refused = client.post(
        f"/api/transactions/{txn_id}/payment/confirm",
        json={"razorpay_payment_id": "pay_x", "razorpay_signature": "0" * 64},
    )
    assert refused.status_code == 409
    assert "no payment order" in refused.json()["detail"].lower()


def test_config_endpoint_never_leaks_the_key_secret(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_public123")
    monkeypatch.setattr(settings, "razorpay_key_secret", "SUPERSECRETVALUE")

    body = client.get("/api/config").json()
    assert body["razorpay_key_id"] == "rzp_test_public123"
    assert "SUPERSECRETVALUE" not in str(body)
    assert "secret" not in str(body).lower()
