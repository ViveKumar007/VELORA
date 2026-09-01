"""Pull live products into Velora's catalog.

    python -m app.sync_catalog --list
    python -m app.sync_catalog --terms milk,bread,ketchup --platforms BlinkIt,Zepto
    python -m app.sync_catalog --preset groceries --dry-run

What this replaces: `catalog_seed.py` invented fourteen products so the demo
had something to buy. This fetches real ones, at real prices, from real
Indian quick-commerce platforms -- so the gate is deciding about a purchase
that could actually be made, not about a fixture.

Nothing downstream changes. The gate, the matcher, the scorer and the payment
flow all read the products table and cannot tell where a row came from. That
is the point of having made the catalog the price authority in the first
place.

Credits: one per platform per search term. The trial pack is 100, so the cost
is printed and confirmed before anything is spent.
"""

from __future__ import annotations

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    # The Windows console is cp1252 and cannot encode the rupee sign; without
    # this the script dies while printing a price it already fetched.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Merchant, Product, utcnow  # noqa: E402
from app.services import quickcommerce as qc  # noqa: E402
from app.utils.money import format_inr, rupees_to_paise  # noqa: E402

#: Search terms grouped by the category Velora files them under.
#:
#: The API returns no category, and guessing one from a product name is how a
#: grocery policy ends up approving a phone. The term we searched *is* the
#: category evidence, so it is recorded rather than inferred.
PRESETS: dict[str, dict[str, list[str]]] = {
    "groceries": {
        "groceries": [
            "milk", "bread", "eggs", "butter", "rice", "atta",
            "tomato ketchup", "onion", "tomato", "paneer", "curd",
            "cooking oil", "sugar", "salt", "tea", "coffee",
        ]
    },
    "pantry": {
        "groceries": ["pasta", "cheese", "olive oil", "garlic", "spices", "noodles"]
    },
    "electronics": {
        "electronics": ["wireless earbuds", "bluetooth headphones", "power bank", "usb charger"]
    },
}


def _merchant_for(db, merchant_name: str) -> Merchant:
    """Find or create the merchant row a synced product belongs to.

    Created merchants are agent-ready but have no login: they are storefronts
    Velora knows about, not accounts anyone signs into. A buyer policy that
    does not list them will refuse their products, which is the gate working.
    """
    merchant = db.scalars(select(Merchant).where(Merchant.name == merchant_name)).first()
    if merchant is not None:
        return merchant

    slug = merchant_name.lower().replace(" ", "-")
    merchant = Merchant(
        slug=slug,
        name=merchant_name,
        description=f"{merchant_name}, synced from the QuickCommerce API.",
        categories=[],
        agent_ready=True,
        status="ACTIVE",
    )
    db.add(merchant)
    db.flush()
    print(f"    + new merchant: {merchant_name}")
    return merchant


def _upsert(db, item: dict, category: str) -> str:
    """Insert or refresh one product. Returns 'added' or 'updated'.

    Matched on (name, merchant) rather than on the platform's id, because
    Product has no column for a foreign id and adding one would need a
    migration -- create_all does not alter existing tables. The external id
    still travels, in attributes, so a row can be traced back to its source.
    """
    price_paise = rupees_to_paise(item["price_rupees"])
    attributes = {
        "source": "quickcommerce",
        "platform": item["platform"],
        "external_id": item["external_id"],
        "quantity": item["quantity"],
        "brand": item["brand"],
        "mrp_rupees": item["mrp"],
        "deeplink": item["deeplink"],
        "inventory": item["inventory"],
        "store_id": item["store_id"],
        "sponsored": item["is_ad"],
        "synced_at": utcnow().isoformat(),
    }

    existing = db.scalars(
        select(Product).where(Product.name == item["name"], Product.merchant == item["merchant"])
    ).first()

    if existing is not None:
        existing.price_paise = price_paise
        existing.rating = item["rating"]
        existing.category = category
        existing.in_stock = True
        existing.attributes = attributes
        return "updated"

    merchant = _merchant_for(db, item["merchant"])
    # The description carries the generic noun we searched for. The relevance
    # matcher reads name + description + category, so a product called
    # "Amul Taaza" is still findable by someone who asked for milk.
    db.add(
        Product(
            name=item["name"],
            description=f"{item['quantity']} {category} · {item['search_term']}".strip(),
            price_paise=price_paise,
            currency="INR",
            category=category,
            merchant=merchant.name,
            merchant_id=merchant.id,
            rating=item["rating"],
            attributes=attributes,
            in_stock=True,
        )
    )
    return "added"


def sync(terms_by_category: dict[str, list[str]], platforms: list[str], *,
         per_term: int, dry_run: bool) -> None:
    total_calls = sum(len(t) for t in terms_by_category.values()) * len(platforms)

    print(f"\nPlatforms : {', '.join(platforms)}")
    print(f"Terms     : {sum(len(t) for t in terms_by_category.values())}")
    print(f"Cost      : {total_calls} credits (1 per platform per term)")

    try:
        summary = qc.credits()
        available = summary.get("total_available", 0)
        print(f"Available : {available} credits")
        if total_calls > available:
            print(f"\nRefusing: this run needs {total_calls} credits and only {available} remain.")
            return
    except qc.QuickCommerceError as exc:
        print(f"\nCould not check credits: {exc}")
        return

    if dry_run:
        print("\n-- dry run: the API is still called (that is what costs credits),")
        print("   but nothing is written to the database.\n")

    db = SessionLocal()
    added = updated = skipped = 0
    try:
        for category, terms in terms_by_category.items():
            for term in terms:
                for platform in platforms:
                    try:
                        items = qc.search(term, platform, limit=per_term)
                    except qc.QuickCommerceError as exc:
                        print(f"  {platform:<10} {term:<18} failed: {exc}")
                        continue

                    if not items:
                        print(f"  {platform:<10} {term:<18} nothing available")
                        skipped += 1
                        continue

                    for item in items:
                        item["search_term"] = term
                        if dry_run:
                            print(f"  {platform:<10} {term:<18} "
                                  f"{format_inr(rupees_to_paise(item['price_rupees'])):>10}  {item['name']}")
                            continue
                        result = _upsert(db, item, category)
                        added += result == "added"
                        updated += result == "updated"

                    if not dry_run:
                        db.commit()
                        print(f"  {platform:<10} {term:<18} {len(items)} item(s)")

        if not dry_run:
            db.commit()
            total = db.scalar(select(func.count()).select_from(Product)) or 0
            print(f"\nAdded {added}, updated {updated}. Catalog now holds {total} products.")
            print("No restart needed — the app reads products from the database per request.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync live products into Velora's catalog.")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="A ready-made set of search terms.")
    parser.add_argument("--terms", help="Comma-separated search terms (filed under --category).")
    parser.add_argument("--category", default="groceries", help="Category for --terms. Default: groceries.")
    parser.add_argument("--platforms", default="BlinkIt,Zepto",
                        help="Comma-separated. Default: BlinkIt,Zepto.")
    parser.add_argument("--per-term", type=int, default=3, help="Max products kept per term per platform.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print; write nothing.")
    parser.add_argument("--list", action="store_true", help="Show credits and presets, then exit. Free.")
    args = parser.parse_args()

    if not qc.is_configured():
        print("QUICKCOMMERCE_API_KEY is not set in backend/.env.")
        raise SystemExit(1)

    if args.list:
        try:
            summary = qc.credits()
            print(f"Credits available : {summary.get('total_available')}")
            print(f"Credits used      : {summary.get('total_used')}")
        except qc.QuickCommerceError as exc:
            print(f"Could not check credits: {exc}")
        print("\nPresets:")
        for name, groups in PRESETS.items():
            count = sum(len(t) for t in groups.values())
            print(f"  {name:<12} {count} terms  ({count} credits per platform)")
        print("\nPlatforms:", ", ".join(qc.PLATFORM_TO_MERCHANT))
        return

    if args.preset:
        terms_by_category = PRESETS[args.preset]
    elif args.terms:
        terms = [t.strip() for t in args.terms.split(",") if t.strip()]
        terms_by_category = {args.category: terms}
    else:
        parser.error("Give either --preset or --terms (or --list to see options).")

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    unknown = [p for p in platforms if p not in qc.PLATFORM_TO_MERCHANT]
    if unknown:
        parser.error(f"Unknown platform(s): {', '.join(unknown)}")

    sync(terms_by_category, platforms, per_term=args.per_term, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
