"""Payment provider callbacks.

Signature verification runs over the raw request body. Re-serialising parsed
JSON would change the bytes and break the HMAC, so the raw body is read
directly and only parsed after the signature checks out.

Unverified webhooks are rejected outright. An unauthenticated endpoint that
moves transactions to PAYMENT_SUCCESS would hand anyone on the internet the
power to mark purchases paid.
"""

import json

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.models import TransactionRequest
from app.schemas.api import SimulatePaymentIn, TransactionView
from app.services import events
from app.services.payments import get_provider
from app.services.payments.stub import StubPaymentProvider
from app.services.payments_flow import handle_webhook_event

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/payment")
async def payment_webhook(
    request: Request,
    db: DbSession,
    x_razorpay_signature: str | None = Header(default=None),
    x_velora_signature: str | None = Header(default=None),
):
    provider = get_provider()

    # The stub's signing secret ships in the source tree, so in stub mode this
    # endpoint would accept a forged, correctly-signed webhook from anyone who
    # could reach it -- driving PAYMENT_CREATED straight to PAYMENT_SUCCESS.
    # The stub has its own authenticated /simulate route for demos, so the
    # public one is closed unless a real provider is configured.
    if isinstance(provider, StubPaymentProvider):
        raise HTTPException(
            status_code=404,
            detail=(
                "No payment webhook is configured. The stub provider does not accept "
                "external webhooks; use POST /api/webhooks/simulate instead."
            ),
        )

    raw = await request.body()
    signature = x_razorpay_signature or x_velora_signature or ""

    if not provider.verify_webhook(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook body.") from exc

    txn = handle_webhook_event(db, event)
    if txn is None:
        # Acknowledge unknown orders: retrying will not help the provider.
        return {"received": True, "matched": False}

    events.publish(
        "transaction.payment",
        {"transaction_id": txn.id, "state": txn.state, "payment_id": txn.payment_id},
    )
    return {"received": True, "matched": True, "state": txn.state}


@router.post("/simulate", response_model=TransactionView)
def simulate_payment_result(
    payload: SimulatePaymentIn,
    db: DbSession,
    user: CurrentUser,
):
    """Demo aid: deliver a correctly signed webhook to ourselves.

    Razorpay cannot reach localhost, so without this the payment leg could
    not be shown end to end on a laptop. It runs the real webhook handler
    over a real signature check -- only the delivery is local.
    """
    if not isinstance(get_provider(), StubPaymentProvider):
        raise HTTPException(
            status_code=400,
            detail="Simulation is only available with PAYMENT_PROVIDER=stub.",
        )

    txn = db.get(TransactionRequest, payload.transaction_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such transaction.")
    if not txn.payment_order_id:
        raise HTTPException(
            status_code=409,
            detail="This transaction has no payment order yet.",
        )

    event = StubPaymentProvider.capture_payload(txn.payment_order_id, succeeded=payload.succeed)
    body = json.dumps(event).encode()
    if not get_provider().verify_webhook(body, StubPaymentProvider.sign(body)):
        raise HTTPException(status_code=500, detail="Simulated webhook failed verification.")

    updated = handle_webhook_event(db, event)
    if updated is None:
        raise HTTPException(status_code=404, detail="Webhook did not match a transaction.")

    events.publish(
        "transaction.payment",
        {"transaction_id": updated.id, "state": updated.state},
    )
    return TransactionView.build(updated)
