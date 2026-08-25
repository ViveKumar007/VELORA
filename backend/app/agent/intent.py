"""Turn a shopping request in plain language into a structured intent.

This is deliberately a rules-based parser rather than a model call. It is
fast, free, offline, and above all reproducible -- a demo that must show the
same thing twice cannot depend on sampling. extract_intent() is the seam: a
model-backed implementation can replace it without any other file changing,
because nothing downstream of here can influence an authorization outcome.

Whatever produces the intent, it stays a *proposal*. The agent may only ask
Velora for a product; Velora decides whether it is allowed.
"""

import re
from dataclasses import dataclass, field

from app.utils.money import rupees_to_paise

#: Everyday words mapped to catalog categories.
CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "electronics": (
        "headphone", "headphones", "earbuds", "earphone", "earphones", "speaker",
        "speakers", "audio", "laptop", "phone", "mouse", "keyboard", "charger",
        "watch", "tablet", "camera",
    ),
    "digital_goods": (
        "subscription", "gaming pass", "streaming", "ebook", "software", "license",
        "gift card",
    ),
    "groceries": ("grocery", "groceries", "coffee", "snacks", "tea", "rice"),
    "travel": ("flight", "hotel", "trip", "booking", "cab", "train"),
}

#: Preference keywords mapped to the product attribute they favour.
PREFERENCE_HINTS: dict[str, tuple[str, ...]] = {
    "battery_life": ("battery", "long lasting", "lasts", "playback", "endurance"),
    "rating": ("good", "best", "top rated", "highly rated", "quality", "reliable"),
    "price": ("cheap", "cheapest", "budget", "affordable", "value", "inexpensive"),
    "noise_cancellation": ("noise", "anc", "cancellation", "quiet"),
}

_BUDGET_PATTERNS = (
    r"(?:under|below|less than|within|upto|up to|max(?:imum)?|no more than)\s*"
    r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(k)?",
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(k)?\s*(?:or less|budget|max)",
)


@dataclass
class ShoppingIntent:
    """What the user appears to want. None means 'unspecified', never 'zero'."""

    raw_text: str
    product_query: str = ""
    max_budget_paise: int | None = None
    category: str | None = None
    preferences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "product_query": self.product_query,
            "max_budget_paise": self.max_budget_paise,
            "category": self.category,
            "preferences": list(self.preferences),
        }


def _extract_budget(text: str) -> int | None:
    for pattern in _BUDGET_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        amount = match.group(1).replace(",", "")
        try:
            value = float(amount)
        except ValueError:
            continue
        if match.lastindex and match.lastindex >= 2 and (match.group(2) or "").lower() == "k":
            value *= 1000
        return rupees_to_paise(value)
    return None


def _extract_category(text: str) -> str | None:
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for category, hints in CATEGORY_HINTS.items():
        for hint in hints:
            position = lowered.find(hint)
            if position != -1 and (best is None or position < best[0]):
                best = (position, category)
    return best[1] if best else None


def _extract_preferences(text: str) -> list[str]:
    lowered = text.lower()
    found = [
        preference
        for preference, hints in PREFERENCE_HINTS.items()
        if any(hint in lowered for hint in hints)
    ]
    return found


def _extract_query(text: str) -> str:
    """Strip budget and filler so what remains describes the item."""
    cleaned = re.sub(
        r"(?:under|below|less than|within|upto|up to|max(?:imum)?|no more than)\s*"
        r"(?:rs\.?|inr|₹)?\s*[\d,]+(?:\.\d+)?\s*k?",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^\s*(?:please\s+)?(?:buy|get|find|order|purchase|search for|look for)\s+(?:me\s+)?",
        "",
        cleaned.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bwith\b.*$", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip(" .,")


def extract_intent(text: str) -> ShoppingIntent:
    """Parse a request such as:
    'Buy me wireless headphones under 2,000 with good battery life.'
    """
    return ShoppingIntent(
        raw_text=text,
        product_query=_extract_query(text),
        max_budget_paise=_extract_budget(text),
        category=_extract_category(text),
        preferences=_extract_preferences(text),
    )
