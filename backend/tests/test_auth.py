"""Two doors, and the wall between them.

A buyer sets the spending boundary; a merchant wants sales inside it. Their
interests are opposed, so neither session may reach the other's console.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthError, hash_password, issue_session, read_session, verify_password
from app.main import app
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def anon(db, world):
    """An unauthenticated client, for probing the login doors themselves."""
    from app.api.deps import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Passwords -----------------------------------------------------------


def test_password_hashing_roundtrip():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong", stored)


def test_password_hash_is_salted():
    """Two users with the same password must not share a hash."""
    assert hash_password("same") != hash_password("same")


def test_plaintext_never_appears_in_the_hash():
    stored = hash_password("hunter2")
    assert "hunter2" not in stored


def test_verify_survives_junk_input():
    assert not verify_password("x", "")
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "pbkdf2_sha256$bad$bad$bad")


# --- Session audience separation -----------------------------------------


def test_a_merchant_session_is_not_a_user_session():
    token = issue_session("mch_1", "merchant")
    assert read_session(token, expect="merchant") == "mch_1"
    with pytest.raises(AuthError):
        read_session(token, expect="user")


def test_a_user_session_is_not_a_merchant_session():
    token = issue_session("usr_1", "user")
    with pytest.raises(AuthError):
        read_session(token, expect="merchant")


def test_tampered_session_is_rejected():
    token = issue_session("usr_1", "user")
    body, signature = token.split(".", 1)
    forged = f"{body}.{'0' * len(signature)}"
    with pytest.raises(AuthError):
        read_session(forged, expect="user")


def test_expired_session_is_rejected():
    token = issue_session("usr_1", "user", hours=-1)
    with pytest.raises(AuthError):
        read_session(token, expect="user")


# --- Login endpoints -----------------------------------------------------


def test_user_login_succeeds_and_returns_a_session(anon, world):
    response = anon.post(
        "/api/auth/login",
        json={"email": "demo@velora.local", "password": "velora123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token"].startswith("vs_")
    assert body["user"]["email"] == "demo@velora.local"
    # The password hash must never travel to the client.
    assert "password" not in str(body).lower()


def test_merchant_login_succeeds(anon, world):
    response = anon.post(
        "/api/auth/merchant/login",
        json={"email": "demostore@velora.local", "password": "merchant123"},
    )
    assert response.status_code == 200
    assert response.json()["merchant"]["slug"] == "demostore"


def test_wrong_password_is_refused(anon, world):
    response = anon.post(
        "/api/auth/login",
        json={"email": "demo@velora.local", "password": "not-it"},
    )
    assert response.status_code == 401


def test_unknown_account_and_wrong_password_are_indistinguishable(anon, world):
    """Different messages would let an attacker enumerate valid accounts."""
    wrong_password = anon.post(
        "/api/auth/login", json={"email": "demo@velora.local", "password": "nope"}
    )
    no_such_user = anon.post(
        "/api/auth/login", json={"email": "ghost@velora.local", "password": "nope"}
    )

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json()["detail"] == no_such_user.json()["detail"]


# --- The wall, over HTTP -------------------------------------------------


def test_merchant_session_cannot_reach_the_buyer_console(anon, world):
    """The one that matters: a seller must not read a buyer's policies,
    approvals or dashboard."""
    for path in ["/api/policies", "/api/dashboard", "/api/approvals", "/api/agents"]:
        response = anon.get(path, headers=world["merchant_auth"])
        assert response.status_code == 401, f"{path} accepted a merchant session"


def test_buyer_session_cannot_reach_the_merchant_console(anon, world):
    response = anon.get("/api/merchants/me", headers=world["auth"])
    assert response.status_code == 401


def test_each_session_reaches_its_own_console(anon, world):
    assert anon.get("/api/policies", headers=world["auth"]).status_code == 200
    assert anon.get("/api/merchants/me", headers=world["merchant_auth"]).status_code == 200


def test_buyer_console_requires_a_session(anon, world):
    assert anon.get("/api/policies").status_code == 401
    assert anon.get("/api/dashboard").status_code == 401


def test_merchant_console_requires_a_session(anon, world):
    assert anon.get("/api/merchants/me").status_code == 401


def test_merchant_revenue_is_not_public(anon, world):
    """A public /{slug} exists, but it carries no takings."""
    profile = anon.get("/api/merchants/demostore")
    assert profile.status_code == 200
    body = profile.json()
    assert "revenue_paise" not in body
    assert "password_hash" not in body


def test_agent_catalog_stays_public(anon, world):
    """An external AI buyer must be able to read the storefront without an
    account -- that is the point of publishing it."""
    assert anon.get("/api/merchants/catalog").status_code == 200


def test_merchant_email_is_not_in_the_public_catalog(anon, world):
    """MerchantOut is public. A seller's contact address is not."""
    catalog = anon.get("/api/merchants/catalog").json()
    assert catalog["merchants"], "expected at least one merchant"
    for merchant in catalog["merchants"]:
        assert "email" not in merchant
        assert "password_hash" not in merchant


def test_merchant_sees_their_own_email_in_their_console(anon, world):
    body = anon.get("/api/merchants/me", headers=world["merchant_auth"]).json()
    assert body["merchant"]["email"] == "demostore@velora.local"
    assert "password_hash" not in str(body)
