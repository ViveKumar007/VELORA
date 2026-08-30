"""Velora API.

    AI decides what to do. Velora decides what it is allowed to do.

The route layer is thin by design: it authenticates, validates shapes and
delegates. Every authorization decision lives in app/gate, and every state
change goes through app/services, so no rule can be quietly re-implemented
in an endpoint.
"""

from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    agents,
    auth,
    approvals,
    catalog,
    dashboard,
    gate,
    merchants,
    policies,
    transactions,
    webhooks,
)
from app.config import settings
from app.schemas.api import PublicConfig
from app.services.payments import get_provider

app = FastAPI(
    title="Velora",
    description=(
        "A trust, authorization and audit layer for agentic commerce. "
        "Define the boundary. Let AI do the rest."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Idempotent-Replay"],
)

for router in (
    auth.router,
    catalog.router,
    merchants.router,
    agents.router,
    policies.router,
    gate.router,
    transactions.router,
    approvals.router,
    webhooks.router,
    dashboard.router,
):
    app.include_router(router)


@app.get("/api/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "service": "velora",
        "payment_provider": getattr(get_provider(), "name", "unknown"),
    }


@app.get("/api/config", response_model=PublicConfig, tags=["meta"])
def public_config():
    """Non-secret runtime settings for the frontend.

    razorpay_key_id is the publishable half of the pair and is meant to be
    visible in the browser -- Razorpay Checkout needs it. The key secret is
    never returned by any endpoint.
    """
    provider = get_provider()
    return PublicConfig(
        payment_provider=getattr(provider, "name", "unknown"),
        razorpay_key_id=settings.razorpay_key_id,
        payment_methods=_cached_methods(provider),
    )


@lru_cache(maxsize=1)
def _cached_methods_inner(provider_name: str) -> tuple[tuple[str, bool], ...] | None:
    provider = get_provider()
    getter = getattr(provider, "enabled_methods", None)
    if getter is None:
        return None
    methods = getter()
    return tuple(sorted(methods.items())) if methods else None


def _cached_methods(provider) -> dict[str, bool] | None:
    """Cached because it is an outbound HTTP call and the answer is static for
    the life of the process. Cached as a tuple so lru_cache can hold it."""
    cached = _cached_methods_inner(getattr(provider, "name", "unknown"))
    return dict(cached) if cached else None
