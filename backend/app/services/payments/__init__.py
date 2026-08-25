from functools import lru_cache

from app.config import settings
from app.services.payments.base import PaymentError, PaymentOrder, PaymentProvider
from app.services.payments.stub import StubPaymentProvider


@lru_cache
def get_provider() -> PaymentProvider:
    """Resolve the configured provider. Defaults to the stub so the system
    runs end to end with no keys and no public webhook URL."""
    if settings.payment_provider.lower() == "razorpay":
        from app.services.payments.razorpay_provider import RazorpayProvider

        return RazorpayProvider()
    return StubPaymentProvider()


__all__ = [
    "get_provider",
    "PaymentProvider",
    "PaymentOrder",
    "PaymentError",
    "StubPaymentProvider",
]
