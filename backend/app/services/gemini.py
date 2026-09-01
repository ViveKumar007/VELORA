"""Gemini, used for exactly one job: reading a shopping request.

The model converts English into a structured intent and stops. It never sees
a policy, never sees a spending limit, never picks a product and never takes
any part in an authorization decision. Everything downstream of it -- which
catalog items match, which one is proposed, and above all whether the
purchase is permitted -- is deterministic code that behaves identically if
this file is deleted.

That is the same boundary the rest of Velora is built on, stated once more at
a new edge: a model may propose, it may never authorise. It is also why an
outage here degrades to the rules parser instead of taking the agent down --
`understand_goal` returns None and the caller falls back.

The API key is read from the server environment and never leaves it. No
endpoint returns it, and the browser never sees it: the frontend asks Velora
for a recommendation, and Velora talks to Gemini.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

#: The shape Gemini must return. Constraining the response to a schema is
#: what makes this a parser rather than a chat: there is no prose to strip,
#: no markdown fence to unwrap, and a malformed answer fails loudly here
#: rather than silently downstream.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "intent": {
            "type": "STRING",
            "enum": ["buy", "cook", "restock", "unknown"],
            "description": "What the person is trying to do.",
        },
        "dish": {
            "type": "STRING",
            "description": "The dish or meal named, if any. Empty string when none.",
        },
        "required_items": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": (
                "Generic shopping items needed, lowercase singular nouns "
                "(e.g. 'pasta', 'milk', 'rice', 'headphones'). Never brand names."
            ),
        },
        "category": {
            "type": "STRING",
            "description": "One of the allowed catalog categories, or empty string.",
        },
        "constraints": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Stated restrictions, e.g. 'under 2000', 'wireless', 'cheapest'.",
        },
        "max_budget_rupees": {
            "type": "NUMBER",
            "description": "Stated budget in rupees. 0 when none was stated.",
        },
        "preferences": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Any of: price, rating, battery_life, noise_cancellation.",
        },
        "ambiguous": {
            "type": "BOOLEAN",
            "description": "True only when the request cannot be acted on without asking.",
        },
        "clarification": {
            "type": "STRING",
            "description": "The one question to ask when ambiguous. Empty otherwise.",
        },
    },
    "required": [
        "intent",
        "dish",
        "required_items",
        "category",
        "constraints",
        "max_budget_rupees",
        "preferences",
        "ambiguous",
        "clarification",
    ],
}

_INSTRUCTIONS = """\
You read a shopper's request and describe what they need. You do not choose \
products and you do not see prices.

Rules:
- Return generic item nouns, never brand names and never product titles.
- For a dish, list the ingredients that dish actually requires. "make pasta" \
needs pasta; it does not need headphones.
- Only use a category from this list, or "" if none fits: {categories}.
- Set ambiguous=true ONLY when you genuinely cannot tell what is wanted \
(for example "buy me something nice"). A request naming a dish, a meal or a \
product type is NOT ambiguous.
- When ambiguous, put one short question in `clarification`.
- max_budget_rupees is the number the shopper stated, or 0.

The catalog sells, broadly: {vocabulary}. Use this only to judge which \
category fits; do not restrict the ingredients you list to it, and do not \
name catalog products.

Request: {goal}
"""


def _payload(goal: str, categories: list[str], vocabulary: str) -> dict[str, Any]:
    prompt = _INSTRUCTIONS.format(
        categories=", ".join(categories) or "none",
        vocabulary=vocabulary or "general goods",
        goal=goal,
    )
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            # Temperature 0: the demo has to tell the same story twice, and a
            # parser that samples is not a parser.
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }


def is_configured() -> bool:
    return bool(settings.gemini_api_key)


#: Parsed goals, keyed by the exact request. Two things make this safe: the
#: call is at temperature 0, so the same sentence already had to produce the
#: same reading; and the value cached is an *interpretation*, never a price,
#: a policy or a decision -- all of which are re-read from the database on
#: every request regardless.
#:
#: It earns its place because observed latency ranges from 4s to over 20s,
#: and a demo presses the same four preset goals over and over. The second
#: press should not gamble on the API being fast that time.
_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}
_CACHE_LIMIT = 256


def clear_cache() -> None:
    _CACHE.clear()


def understand_goal(
    goal: str, *, categories: list[str], vocabulary: str = ""
) -> dict[str, Any] | None:
    """Ask Gemini to describe a request. Returns None on any failure.

    Every error path is a None, never an exception: the agent console must
    keep working when the key is missing, the quota is spent, or the model is
    overloaded. A degraded parse is a worse answer; a 500 is a broken product.
    """
    if not is_configured():
        return None

    key = (settings.gemini_model, goal.strip().lower(), ",".join(categories))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    try:
        response = httpx.post(
            ENDPOINT.format(model=settings.gemini_model),
            params={"key": settings.gemini_api_key},
            json=_payload(goal, categories, vocabulary),
            timeout=settings.gemini_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning(
            "Gemini rejected the request (%s): %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Gemini call failed: %s", exc)
        return None

    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        log.warning("Gemini returned no usable candidate: %s", str(body)[:300])
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Gemini returned non-JSON despite the schema: %s", text[:300])
        return None

    if not isinstance(parsed, dict):
        return None

    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key] = parsed
    return parsed
