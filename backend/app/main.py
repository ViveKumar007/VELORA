"""Velora API.

    AI decides what to do. Velora decides what it is allowed to do.

The route layer is thin by design: it authenticates, validates shapes and
delegates. Every authorization decision lives in app/gate, and every state
change goes through app/services, so no rule can be quietly re-implemented
in an endpoint.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    agents,
    approvals,
    catalog,
    dashboard,
    gate,
    policies,
    transactions,
    webhooks,
)
from app.config import settings
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
    catalog.router,
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
