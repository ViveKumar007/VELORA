"""QuickCommerce API client: live product and price data from Indian
quick-commerce and marketplace platforms.

Velora's catalog is the price authority the gate trusts. An agent sends only
a product_id; price, category and merchant are read server-side, which is the
only reason a spending limit means anything. That makes this module's job
narrow and serious: whatever it writes into the products table is what
Velora will later authorize against.

So it validates rather than imports. An item with no price, no name, or
marked unavailable is dropped, not guessed at. Prices are converted to
integer paise exactly once, through the same helper the rest of the product
uses. A bad row here is a bad authorization decision later.

Deliberately offline from the request path. Nothing in the gate, the scoring
or the payment flow ever calls this — it runs from the sync command, writes
rows, and stops. Authorization stays deterministic and never waits on a
third-party network call.

Credits: /v1/search costs 1 credit per platform per call. /v1/credits and
/v1/supported-platforms are free. The trial pack is small, so the sync
command prints its cost before spending anything.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.quickcommerceapi.com"

#: API platform name -> the merchant name Velora already stores.
#:
#: This mapping is not cosmetic. Product.merchant is a denormalised string and
#: authorization policies match on it directly ("allowed_merchants":
#: ["Blinkit", "Zepto"]). The API says "BlinkIt"; the database says "Blinkit".
#: Importing the API's spelling would have created products that every
#: existing grocery policy silently refused as MERCHANT_NOT_ALLOWED.
PLATFORM_TO_MERCHANT: dict[str, str] = {
    "BlinkIt": "Blinkit",
    "Zepto": "Zepto",
    "Swiggy": "Swiggy",
    "BigBasket": "BigBasket",
    "DMart": "DMart",
    "JioMart": "JioMart",
    "Minutes": "Flipkart Minutes",
    "Amazon": "Amazon",
    "Nykaa": "Nykaa",
    "Myntra": "Myntra",
    "Flipkart": "Flipkart",
}

#: Platforms the API requires a pincode for.
NEEDS_PINCODE = {"DMart", "JioMart", "Minutes"}


class QuickCommerceError(Exception):
    """The API could not be used. Carries the API's own wording where it has any."""


def is_configured() -> bool:
    return bool(settings.quickcommerce_api_key)


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not is_configured():
        raise QuickCommerceError("QUICKCOMMERCE_API_KEY is not set.")

    try:
        response = httpx.get(
            f"{BASE_URL}{path}",
            params=params or {},
            headers={"X-API-Key": settings.quickcommerce_api_key},
            timeout=settings.quickcommerce_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise QuickCommerceError(f"Could not reach the API: {exc}") from exc

    if response.status_code == 401:
        raise QuickCommerceError("Invalid or missing API key.")
    if response.status_code == 402:
        raise QuickCommerceError("No credits remaining.")
    if response.status_code == 429:
        raise QuickCommerceError("Rate limited (100 req/min). Slow down and retry.")
    if response.status_code >= 400:
        detail = ""
        try:
            detail = str(response.json())[:200]
        except ValueError:
            detail = response.text[:200]
        raise QuickCommerceError(f"HTTP {response.status_code}: {detail}")

    try:
        return response.json()
    except ValueError as exc:
        raise QuickCommerceError("API returned a non-JSON body.") from exc


def credits() -> dict[str, Any]:
    """Remaining credits. Free — this call costs nothing."""
    return _get("/v1/credits").get("summary", {})


def _clean(raw: dict[str, Any], platform: str) -> dict[str, Any] | None:
    """One API product -> the fields Velora needs, or None if unusable.

    Returning None is the common case for a reason: a catalog row that Velora
    cannot price or name is worse than a missing row, because the gate would
    later authorize against it.
    """
    name = (raw.get("name") or "").strip()
    if not name:
        return None

    if raw.get("available") is False:
        return None

    # offer_price is what the shopper actually pays; mrp is the list price.
    # The gate must judge the real amount, so offer_price wins and mrp is
    # kept only as context.
    price = raw.get("offer_price")
    if price in (None, "", 0):
        price = raw.get("mrp")
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None

    brand = (raw.get("brand") or "").strip()
    # Brand-prefixed, because three different "Tomato Ketchup" rows are
    # indistinguishable otherwise -- both to a human reading the ledger and to
    # the name-based dedupe in the sync.
    full_name = f"{brand} {name}".strip() if brand and not name.lower().startswith(brand.lower()) else name

    external_id = str(raw.get("id") or raw.get("item_id") or "").strip()
    if not external_id:
        return None

    rating = raw.get("rating")
    try:
        rating = round(float(rating), 2) if rating is not None else 0.0
    except (TypeError, ValueError):
        rating = 0.0

    return {
        "external_id": external_id,
        "name": full_name[:200],
        "price_rupees": price,
        "rating": rating,
        "platform": platform,
        "merchant": PLATFORM_TO_MERCHANT.get(platform, platform),
        "quantity": (raw.get("quantity") or "").strip(),
        "brand": brand,
        "mrp": raw.get("mrp"),
        "deeplink": raw.get("deeplink") or "",
        "inventory": raw.get("inventory"),
        "store_id": raw.get("store_id"),
        "is_ad": bool(raw.get("is_ad")),
        "image": (raw.get("images") or [None])[0],
    }


def search(
    query: str,
    platform: str,
    *,
    lat: float | None = None,
    lon: float | None = None,
    pincode: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search one platform. Costs 1 credit.

    Returns only items that survived validation, best-ranked first as the API
    ordered them.
    """
    params: dict[str, Any] = {
        "q": query,
        "lat": lat if lat is not None else settings.quickcommerce_lat,
        "lon": lon if lon is not None else settings.quickcommerce_lon,
        "platform": platform,
    }
    if pincode or platform in NEEDS_PINCODE:
        params["pincode"] = pincode or settings.quickcommerce_pincode

    body = _get("/v1/search", params)
    products = (body.get("data") or {}).get("products") or []

    cleaned: list[dict[str, Any]] = []
    for raw in products:
        item = _clean(raw, platform)
        if item is not None:
            cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned
