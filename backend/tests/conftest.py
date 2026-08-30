"""Integration test fixtures.

These tests need a real PostgreSQL database: they exercise row locks, unique
constraints and JSONB, none of which SQLite can stand in for. Point
TEST_DATABASE_URL at a scratch database -- it is dropped and recreated on
every run.

Skipped automatically when no database is reachable, so the pure unit tests
still run anywhere.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/velora_test"),
)


def _database_reachable(url: str) -> bool:
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _database_reachable(TEST_URL),
    reason=f"No database reachable at {TEST_URL}. Set TEST_DATABASE_URL to run these.",
)


@pytest.fixture(autouse=True)
def force_stub_provider(monkeypatch):
    """Never let the suite touch a live payment provider.

    The tests previously inherited PAYMENT_PROVIDER from .env. The moment the
    app was switched to Razorpay for real, the suite silently started calling
    Razorpay's API -- slow, flaky, dependent on someone's keys being present,
    and capable of creating real orders as a side effect of running tests.

    Autouse and unconditional: a test that wants the Razorpay provider must
    ask for it explicitly rather than inheriting it by accident.
    """
    from app.config import settings
    from app.services.payments import get_provider

    monkeypatch.setattr(settings, "payment_provider", "stub")
    get_provider.cache_clear()
    yield
    get_provider.cache_clear()


@pytest.fixture(scope="session")
def engine():
    from app.models import Base

    eng = create_engine(TEST_URL, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine):
    """A clean database for each test."""
    from app.models import Base

    for table in reversed(Base.metadata.sorted_tables):
        with engine.begin() as conn:
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))

    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def world(db):
    """A seeded user, agent, policy and catalog matching the demo."""
    from datetime import timedelta

    from app.models import (
        Agent,
        AgentStatus,
        AuthorizationPolicy,
        PolicyStatus,
        Product,
        User,
        utcnow,
    )
    from app.auth import hash_password, issue_session
    from app.models import Merchant
    from app.security import generate_agent_token
    from app.utils.money import rupees_to_paise

    now = utcnow()
    user = User(
        name="Demo User",
        email="demo@velora.local",
        password_hash=hash_password("velora123"),
    )
    db.add(user)
    db.flush()

    raw_token, token_hash = generate_agent_token()
    agent = Agent(
        user_id=user.id,
        name="Shopping Agent",
        agent_type="shopping",
        status=AgentStatus.ACTIVE,
        token_hash=token_hash,
    )
    db.add(agent)
    db.flush()

    policy = AuthorizationPolicy(
        user_id=user.id,
        agent_id=agent.id,
        name="Headphones budget",
        max_per_transaction_paise=rupees_to_paise(2000),
        total_budget_paise=rupees_to_paise(2000),
        approval_threshold_paise=rupees_to_paise(1500),
        currency="INR",
        allowed_categories=["electronics"],
        allowed_merchants=["DemoStore"],
        max_transactions=1,
        one_time_use=True,
        valid_from=now,
        expires_at=now + timedelta(minutes=30),
        status=PolicyStatus.ACTIVE,
    )
    db.add(policy)

    products = {
        "lite": Product(
            name="SoundBeat Lite", description="", price_paise=rupees_to_paise(1299),
            currency="INR", category="electronics", merchant="DemoStore",
            rating=4.2, attributes={"battery_hours": 30}, in_stock=True,
        ),
        "pro": Product(
            name="SoundBeat Pro", description="", price_paise=rupees_to_paise(1799),
            currency="INR", category="electronics", merchant="DemoStore",
            rating=4.6, attributes={"battery_hours": 50}, in_stock=True,
        ),
        "premium": Product(
            name="Premium Audio Max", description="", price_paise=rupees_to_paise(2499),
            currency="INR", category="electronics", merchant="DemoStore",
            rating=4.8, attributes={"battery_hours": 60}, in_stock=True,
        ),
        "subscription": Product(
            name="Gaming Subscription", description="", price_paise=rupees_to_paise(999),
            currency="INR", category="digital_goods", merchant="DemoStore",
            rating=4.1, attributes={}, in_stock=True,
        ),
    }
    for product in products.values():
        db.add(product)
    db.commit()

    merchant = Merchant(
        slug="demostore",
        name="DemoStore",
        description="Test merchant.",
        categories=["electronics"],
        email="demostore@velora.local",
        password_hash=hash_password("merchant123"),
        agent_ready=True,
        status="ACTIVE",
    )
    db.add(merchant)
    db.commit()

    return {
        "user": user,
        "agent": agent,
        "policy": policy,
        "token": raw_token,
        "products": products,
        "merchant": merchant,
        # Ready-made sessions so tests exercise real auth rather than a
        # bypass. A test that wants to prove auth works signs in properly.
        "session": issue_session(user.id, "user"),
        "merchant_session": issue_session(merchant.id, "merchant"),
        "auth": {"Authorization": f"Bearer {issue_session(user.id, 'user')}"},
        "merchant_auth": {
            "Authorization": f"Bearer {issue_session(merchant.id, 'merchant')}"
        },
    }
