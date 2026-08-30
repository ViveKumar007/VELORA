"""Payment provider boundary.

Velora talks to money through this interface and nothing else. Two reasons:
the demo must not depend on a live provider or a public webhook URL, and
swapping Razorpay for anything else must not touch the authorization code.

Note what the interface does NOT expose: there is no way to reach it without
an already-approved transaction. Provider objects are constructed in
services/payments/__init__.py and used only by services/payments_flow.py,
which refuses to act on any transaction the gate has not cleared.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class PaymentError(Exception):
    """The provider could not create or process a payment.

    This is emphatically not an authorization failure. Callers must record it
    as PAYMENT_CREATION_FAILED so the audit trail keeps
    'authorization succeeded' and 'payment succeeded' as separate facts.
    """


@dataclass
class PaymentOrder:
    order_id: str
    amount_paise: int
    currency: str
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PaymentProvider(Protocol):
    name: str

    def create_order(
        self,
        *,
        amount_paise: int,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> PaymentOrder:
        """Create an order with the provider. Raises PaymentError on failure."""
        ...

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Return True only if the payload genuinely came from the provider."""
        ...

    def verify_payment_signature(
        self, order_id: str, payment_id: str, signature: str
    ) -> bool:
        """Verify a checkout result handed back by the browser.

        The browser is not trusted. After Razorpay Checkout completes it
        returns a payment id and a signature over "order_id|payment_id"; only
        a party holding the key secret could have produced it. Without this
        check, any client could POST "I paid" and settle a transaction.
        """
        ...
