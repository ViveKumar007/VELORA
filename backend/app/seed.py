"""Create the schema and a demo world.

Run:  python -m app.seed          (idempotent; re-running keeps existing data)
      python -m app.seed --reset  (drop everything first)

Two agents with different boundaries, against one shared storefront:

  Shopping Agent  electronics from DemoStore, max 2,000/purchase, auto <= 1,500
  Grocery Agent   groceries from Blinkit + Zepto, max 500/purchase, auto <= 300

The catalog is arranged so each policy can reach every decision path,
including a price block that has a recoverable in-policy alternative.
"""

import sys
from datetime import timedelta

from sqlalchemy import func, select

# The Windows console defaults to cp1252, which cannot encode the rupee sign.
# Without this, printing a formatted amount raises and the one-time agent
# token is lost after the data has already been committed.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.catalog_seed import MERCHANTS, PRODUCTS  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Agent,
    AgentStatus,
    AuthorizationPolicy,
    Base,
    Merchant,
    PolicyStatus,
    Product,
    User,
    utcnow,
)
from app.auth import hash_password  # noqa: E402
from app.security import generate_agent_token  # noqa: E402
from app.utils.money import format_inr, rupees_to_paise  # noqa: E402


#: Demo credentials. Fine for a seeded local demo; obviously not for anything
#: reachable. Both consoles print them at the end of a seed run.
USER_PASSWORD = "velora123"
MERCHANT_PASSWORD = "merchant123"


def _ensure_merchants(db) -> dict[str, Merchant]:
    by_slug: dict[str, Merchant] = {}
    for item in MERCHANTS:
        merchant = db.scalars(
            select(Merchant).where(Merchant.slug == item["slug"])
        ).first()
        if merchant is None:
            merchant = Merchant(
                slug=item["slug"],
                name=item["name"],
                description=item["description"],
                categories=item["categories"],
                email=f'{item["slug"]}@velora.local',
                password_hash=hash_password(MERCHANT_PASSWORD),
                agent_ready=True,
                status="ACTIVE",
            )
            db.add(merchant)
            db.flush()
        by_slug[item["slug"]] = merchant
    return by_slug


def _ensure_products(db, merchants: dict[str, Merchant]) -> None:
    for item in PRODUCTS:
        exists = db.scalars(select(Product).where(Product.name == item["name"])).first()
        if exists:
            continue
        merchant = merchants[item["merchant"]]
        db.add(
            Product(
                name=item["name"],
                description=item["description"],
                price_paise=rupees_to_paise(item["price"]),
                currency="INR",
                category=item["category"],
                merchant=merchant.name,
                merchant_id=merchant.id,
                rating=item["rating"],
                attributes=item["attributes"],
                in_stock=True,
            )
        )
    db.flush()


def _ensure_agent(db, user, name: str, agent_type: str) -> tuple[Agent, str | None]:
    agent = db.scalars(
        select(Agent).where(Agent.user_id == user.id, Agent.name == name)
    ).first()
    if agent is not None:
        return agent, None

    raw_token, token_hash = generate_agent_token()
    agent = Agent(
        user_id=user.id,
        name=name,
        agent_type=agent_type,
        status=AgentStatus.ACTIVE,
        token_hash=token_hash,
    )
    db.add(agent)
    db.flush()
    return agent, raw_token


def _ensure_policy(db, user, agent, **spec) -> AuthorizationPolicy:
    policy = db.scalars(
        select(AuthorizationPolicy).where(AuthorizationPolicy.agent_id == agent.id)
    ).first()
    if policy is not None:
        return policy

    now = utcnow()
    policy = AuthorizationPolicy(
        user_id=user.id,
        agent_id=agent.id,
        name=spec["name"],
        max_per_transaction_paise=rupees_to_paise(spec["max_per_transaction"]),
        total_budget_paise=rupees_to_paise(spec["total_budget"]),
        approval_threshold_paise=rupees_to_paise(spec["approval_threshold"]),
        currency="INR",
        allowed_categories=spec["categories"],
        allowed_merchants=spec["merchants"],
        max_transactions=spec["max_transactions"],
        one_time_use=spec["one_time_use"],
        valid_from=now,
        expires_at=now + timedelta(minutes=spec.get("expires_in_minutes", 30)),
        status=PolicyStatus.ACTIVE,
    )
    db.add(policy)
    db.flush()
    return policy


def _describe(policy: AuthorizationPolicy) -> str:
    return (
        f"max {format_inr(policy.max_per_transaction_paise)}/purchase, "
        f"budget {format_inr(policy.total_budget_paise)}, "
        f"auto-approve at or below {format_inr(policy.approval_threshold_paise)}"
    )


def seed(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")

    Base.metadata.create_all(engine)
    print("Schema is up to date.")

    db = SessionLocal()
    try:
        user = db.scalars(select(User).limit(1)).first()
        if user is None:
            user = User(
                name="Demo User",
                email="demo@velora.local",
                password_hash=hash_password(USER_PASSWORD),
            )
            db.add(user)
            db.flush()

        merchants = _ensure_merchants(db)
        _ensure_products(db, merchants)

        shopper, shopper_token = _ensure_agent(db, user, "Shopping Agent", "shopping")
        electronics = _ensure_policy(
            db, user, shopper,
            name="Headphones budget",
            max_per_transaction=2000, total_budget=2000, approval_threshold=1500,
            categories=["electronics"], merchants=["DemoStore"],
            max_transactions=1, one_time_use=True,
        )

        grocer, grocer_token = _ensure_agent(db, user, "Grocery Agent", "shopping")
        groceries = _ensure_policy(
            db, user, grocer,
            name="Weekly groceries",
            max_per_transaction=500, total_budget=2000, approval_threshold=300,
            categories=["groceries"], merchants=["Blinkit", "Zepto"],
            max_transactions=5, one_time_use=False, expires_in_minutes=120,
        )

        db.commit()

        merchant_count = db.scalar(select(func.count()).select_from(Merchant)) or 0
        product_count = db.scalar(select(func.count()).select_from(Product)) or 0

        print("\n" + "=" * 68)
        print("VELORA DEMO WORLD")
        print("=" * 68)
        print(f"User        {user.id}  {user.email}")
        print(f"Storefront  {merchant_count} merchants, {product_count} products")
        print()
        for agent, policy, token in (
            (shopper, electronics, shopper_token),
            (grocer, groceries, grocer_token),
        ):
            print(f"{agent.name}")
            print(f"  agent     {agent.id}")
            print(f"  policy    {policy.name} -- {_describe(policy)}")
            print(f"            categories={policy.allowed_categories} "
                  f"merchants={policy.allowed_merchants}")
            if token:
                print(f"  TOKEN     {token}")
            else:
                print("  TOKEN     (already existed; use --reset to mint a fresh one)")
            print()
        print("Tokens are shown once. Use as:  Authorization: Bearer <token>")
        print()
        print("-" * 68)
        print("SIGN IN")
        print("-" * 68)
        print(f"  Buyer console     {user.email} / {USER_PASSWORD}")
        print("  Merchant console  <slug>@velora.local / " + MERCHANT_PASSWORD)
        print("                    e.g. blinkit@velora.local, demostore@velora.local")
        print("=" * 68 + "\n")

    finally:
        db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
