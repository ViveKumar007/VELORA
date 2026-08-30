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

    def enabled_methods(self) -> dict[str, bool] | None:
        """Which payment methods this account can actually accept.

        Razorpay enables methods per account, and an unactivated test account
        typically has UPI off. Offering a disabled method produces a dead end
        that looks like a bug in our app, so we ask and only show what works.

        Returns None on any failure: an unavailable methods list should degrade
        to "show everything", never to "show nothing".
        """
        import json
        import urllib.error
        import urllib.request

        url = f"https://api.razorpay.com/v1/methods?key_id={settings.razorpay_key_id}"
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, ValueError, TimeoutError):
            return None

        # Keep only the simple on/off flags Checkout understands as `method`.
        wanted = ("card", "netbanking", "wallet", "upi", "emi", "paylater", "cardless_emi")
        methods = {k: bool(payload.get(k)) for k in wanted if k in payload}

        # netbanking and wallet arrive as dicts of providers, not booleans.
        for key in ("netbanking", "wallet"):
            value = payload.get(key)
            if isinstance(value, dict):
                methods[key] = any(value.values()) if value else False

        return methods or None

    def verify_payment_signature(
        self, order_id: str, payment_id: str, signature: str
    ) -> bool:
        """HMAC-SHA256 over "order_id|payment_id", keyed with the API secret.

        This is Razorpay's documented client-callback scheme. Note it uses the
        KEY SECRET, not the webhook secret -- they are different credentials
        and mixing them up fails silently in the safe direction (rejection).
        """
        if not order_id or not payment_id or not signature:
            return False
        expected = hmac.new(
            settings.razorpay_key_secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
