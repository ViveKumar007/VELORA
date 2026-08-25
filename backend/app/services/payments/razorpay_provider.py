"""Razorpay test-mode provider.

Webhook signatures are verified with HMAC-SHA256 over the raw request body,
per Razorpay's documented scheme. The raw bytes matter: re-serialising the
parsed JSON changes the payload and the signature will not match.
"""

import hashlib
import hmac
from typing import Any

from app.config import settings
from app.services.payments.base import PaymentError, PaymentOrder


class RazorpayProvider:
    name = "razorpay"

    def __init__(self) -> None:
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise PaymentError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set to use the "
                "razorpay provider. Set PAYMENT_PROVIDER=stub to run without keys."
            )
        import razorpay  # imported lazily so the stub path needs no SDK

        self._client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )

    def create_order(
        self,
        *,
        amount_paise: int,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> PaymentOrder:
        try:
            order: dict[str, Any] = self._client.order.create(
                {
                    # Razorpay counts in paise, which is what we store.
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": receipt,
                    "notes": notes or {},
                    "payment_capture": 1,
                }
            )
        except Exception as exc:  # provider/network failure, not a policy failure
            raise PaymentError(f"Razorpay could not create the order: {exc}") from exc

        return PaymentOrder(
            order_id=order["id"],
            amount_paise=int(order["amount"]),
            currency=order["currency"],
            provider=self.name,
            raw=order,
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        secret = settings.razorpay_webhook_secret
        if not secret:
            # Fail closed: an unverifiable webhook is not a trusted webhook.
            return False
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")
