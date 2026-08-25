"""Create the schema and a demo world.

Run:  python -m app.seed          (idempotent; re-running keeps existing data)
      python -m app.seed --reset  (drop everything first)

The catalog is built to make all four decision paths reachable against the
default policy: one product auto-approves, one escalates, one breaks the
amount limit, one breaks the category rule.
"""

import sys
from datetime import timedelta

from sqlalchemy import func, select

# The Windows console defaults to cp1252, which cannot encode the rupee sign.
# Without this, printing a formatted amount raises and the one-time agent
# token is lost after the data has already been committed.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.db import SessionLocal, engine
from app.models import (
    Agent,
    AgentStatus,
    AuthorizationPolicy,
    Base,
    PolicyStatus,
    Product,
    User,
    utcnow,
)
from app.security import generate_agent_token
from app.utils.money import format_inr, rupees_to_paise

CATALOG = [
    dict(
        name="SoundBeat Lite",
        description="Lightweight wireless headphones with 30 hours of playback.",
        price=1299,
        category="electronics",
        merchant="DemoStore",
        rating=4.2,
        attributes={"battery_hours": 30, "wireless": True},
    ),
    dict(
        name="SoundBeat Pro",
        description="Wireless headphones with 50 hours of playback and deep bass.",
        price=1799,
        category="electronics",
        merchant="DemoStore",
        rating=4.6,
        attributes={"battery_hours": 50, "wireless": True, "noise_cancellation": True},
    ),
    dict(
        name="Premium Audio Max",
        description="Flagship over-ear headphones, 60 hours of playback.",
        price=2499,
        category="electronics",
        merchant="DemoStore",
        rating=4.8,
        attributes={"battery_hours": 60, "wireless": True, "noise_cancellation": True},
    ),
    dict(
        name="Gaming Subscription (3 months)",
        description="Cloud gaming pass. Digital goods, not electronics.",
        price=999,
        category="digital_goods",
        merchant="DemoStore",
        rating=4.1,
        attributes={"duration_months": 3},
    ),
    dict(
        name="AudioHouse Studio Buds",
        description="Earbuds from a merchant outside the default authorization.",
        price=1499,
        category="electronics",
        merchant="AudioHouse",
        rating=4.4,
        attributes={"battery_hours": 24, "wireless": True},
    ),
]


def reset_schema() -> None:
    Base.metadata.drop_all(engine)
    print("Dropped all tables.")


def seed(reset: bool = False) -> None:
    if reset:
        reset_schema()

    Base.metadata.create_all(engine)
    print("Schema is up to date.")

    db = SessionLocal()
    try:
        user = db.scalars(select(User).limit(1)).first()
        if user is None:
            user = User(name="Demo User", email="demo@velora.local")
            db.add(user)
            db.flush()
            print(f"Created user {user.id} ({user.email})")

        for item in CATALOG:
            exists = db.scalars(select(Product).where(Product.name == item["name"])).first()
            if exists:
                continue
            db.add(
                Product(
                    name=item["name"],
                    description=item["description"],
                    price_paise=rupees_to_paise(item["price"]),
                    currency="INR",
                    category=item["category"],
                    merchant=item["merchant"],
                    rating=item["rating"],
                    attributes=item["attributes"],
                    in_stock=True,
                )
            )
        db.flush()
        product_count = db.scalar(select(func.count()).select_from(Product)) or 0
        print(f"Catalog ready: {product_count} products.")

        agent = db.scalars(select(Agent).where(Agent.user_id == user.id).limit(1)).first()
        raw_token = None
        if agent is None:
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

        policy = db.scalars(
            select(AuthorizationPolicy)
            .where(AuthorizationPolicy.agent_id == agent.id)
            .limit(1)
        ).first()
        if policy is None:
            now = utcnow()
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
            db.flush()

        db.commit()

        print("\n" + "=" * 62)
        print("VELORA DEMO WORLD")
        print("=" * 62)
        print(f"User          {user.id}  {user.email}")
        print(f"Agent         {agent.id}  {agent.name}")
        print(f"Policy        {policy.id}  {policy.name}")
        print(
            f"              max {format_inr(policy.max_per_transaction_paise)}/purchase, "
            f"budget {format_inr(policy.total_budget_paise)}, "
            f"auto-approve at or below {format_inr(policy.approval_threshold_paise)}"
        )
        print(f"              categories={policy.allowed_categories} "
              f"merchants={policy.allowed_merchants}")
        if raw_token:
            print("\nAGENT TOKEN (shown once -- copy it now):")
            print(f"  {raw_token}")
            print("\n  Use it as:  Authorization: Bearer <token>")
        else:
            print("\nAgent already existed, so no new token was minted.")
            print("Run with --reset to rebuild the demo world and mint a fresh one.")
        print("=" * 62 + "\n")

    finally:
        db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
