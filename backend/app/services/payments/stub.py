"""In-process payment provider.

Runs with no network, no keys and no public webhook URL, which makes the
whole approve/pay/audit flow demonstrable on a laptop. It also lets a failure
be triggered on purpose: pass force_failure in notes and order creation
raises, so the PAYMENT_CREATION_FAILED branch can be shown deliberately
instead of hoping a provider outage happens during a demo.
"""

import hashlib
import hmac
import uuid
from typing import Any

from app.services.payments.base import PaymentError, PaymentOrder

STUB_WEBHOOK_SECRET = "velora_stub_secret"


class StubPaymentProvider:
    name = "stub"

    def create_order(
        self,
        *,
        amount_paise: int,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> PaymentOrder:
        notes = notes or {}
        if notes.get("force_failure") == "true":
            raise PaymentError("Simulated provider outage while creating the order.")
        if amount_paise <= 0:
            raise PaymentError("Order amount must be greater than zero.")

        order_id = f"order_stub_{uuid.uuid4().hex[:14]}"
        return PaymentOrder(
            order_id=order_id,
            amount_paise=amount_paise,
            currency=currency,
            provider=self.name,
            raw={
                "id": order_id,
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
                "status": "created",
                "notes": notes,
            },
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(
            STUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    @staticmethod
    def sign(payload: bytes) -> str:
        """Helper so the demo can produce a validly signed webhook."""
        return hmac.new(STUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()

    @staticmethod
    def capture_payload(order_id: str, succeeded: bool = True) -> dict[str, Any]:
        event = "payment.captured" if succeeded else "payment.failed"
        return {
            "event": event,
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_stub_{uuid.uuid4().hex[:14]}",
                        "order_id": order_id,
                        "status": "captured" if succeeded else "failed",
                        "error_description": None if succeeded else "Card declined by issuer.",
                    }
                }
            },
        }
