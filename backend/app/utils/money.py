"""Money helpers.

Everything inside Velora is an integer count of paise. Rupees exist only in
API payloads and UI strings, and the conversion happens here so it happens
exactly once, in one place.
"""

from decimal import ROUND_HALF_UP, Decimal


def rupees_to_paise(rupees: float | int | str | Decimal) -> int:
    """Convert a rupee amount to paise without float drift."""
    return int((Decimal(str(rupees)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees(paise: int) -> float:
    return float(Decimal(paise) / 100)


def format_inr(paise: int) -> str:
    """Render paise as an Indian-grouped rupee string, e.g. 179900 -> Rs.1,799.

    Uses the 2-2-3 grouping convention (12,34,567) rather than 3-3-3.
    """
    rupees = Decimal(paise) / 100
    whole = int(rupees)
    fraction = rupees - whole
    sign = "-" if whole < 0 else ""
    digits = str(abs(whole))

    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts) + "," + tail
    else:
        grouped = digits

    if fraction:
        return f"{sign}₹{grouped}.{int(abs(fraction) * 100):02d}"
    return f"{sign}₹{grouped}"
