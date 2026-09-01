"""Grounding an intent in the actual catalog.

This module is the reason the agent stopped proposing headphones to someone
who asked how to cook pasta.

The old selection step narrowed by category and, finding nothing, fell back
to *the entire catalog* -- so an unrecognised request degraded into "rank
everything by rating", and the highest-rated product in the shop won no
matter what had been asked for. A recommender that always returns something
is worse than one that admits it has nothing: it launders "I did not
understand you" into a confident answer.

So relevance is a gate, not a score. A product is a candidate only if it
answers something the request actually asked for. When nothing answers it,
the correct output is an empty list, and the agent says so.

Deliberately deterministic and offline. Gemini decides what the shopper
*needs*; this file decides what the catalog *has*, and it would give the same
answer with the network unplugged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import Product

#: Words that carry no shopping meaning and would otherwise match everything.
STOPWORDS = frozenset(
    """
    a an the and or of for to me my i want need get buy some something
    please with without from at in on it that this you your can find make
    cook prepare order purchase looking look would like need needs
    """.split()
)

#: Catalog vocabulary. The left side is what a person says; the right side is
#: what the shelf label happens to read. Kept small and explicit rather than
#: clever -- a wrong synonym here produces a confidently irrelevant match,
#: which is the exact failure this module exists to prevent.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "headphone": ("headphone", "earbud", "earphone", "audio", "soundbeat", "airdopes"),
    "earbud": ("earbud", "headphone", "earphone", "airdopes"),
    "speaker": ("speaker", "audio"),
    "rice": ("rice", "basmati"),
    "vegetable": ("vegetable", "veggie", "veg"),
    "oil": ("oil", "sunflower"),
    "bread": ("bread", "loaf"),
    "egg": ("egg",),
    "milk": ("milk",),
    "butter": ("butter",),
    "subscription": ("subscription", "gaming", "pass"),
    "biryani": ("biryani",),
    "coffee": ("coffee", "espresso"),
    "laptop": ("laptop",),
}


#: Words that turn a mention into a denial. "No Onion" is not onion.
#:
#: This exists because of a real, visible failure: a synced product called
#: "Surabhi Tomato Ketchup No Onion No Garlic" was being returned as the best
#: match for "onion". A shopper asking for onions was offered a sauce whose
#: name says, in words, that it contains none.
NEGATORS = ("no", "without", "zero", "free", "sans", "non")


@dataclass
class Match:
    """One catalog product, and what in the request it answers.

    `strength` records *where* the match landed. A term found in the product's
    own name is real evidence; one found only in a description is weaker, and
    for synced products the description is partly machine-written, so treating
    the two as equal let a generated tag outrank a genuine title.
    """

    product: Product
    matched: list[str] = field(default_factory=list)
    strength: int = 0


def _forms(term: str) -> tuple[str, ...]:
    """Every spelling of a term worth looking for."""
    stem = term.strip().lower()
    stem = re.sub(r"[^a-z0-9 ]+", " ", stem).strip()
    if not stem:
        return ()
    # Crude but sufficient singularisation: the catalog is English nouns.
    if stem.endswith("ies") and len(stem) > 4:
        stem = stem[:-3] + "y"
    elif stem.endswith("es") and len(stem) > 4:
        stem = stem[:-2]
    elif stem.endswith("s") and len(stem) > 3:
        stem = stem[:-1]
    return SYNONYMS.get(stem, (stem,))


def _negated(form: str, haystack: str) -> bool:
    """True when every mention of `form` is denied by a preceding negator.

    Scans up to two words back, so "no onion", "no added sugar" and
    "free from garlic" all read as denials rather than as ingredients.
    """
    pattern = rf"\b{re.escape(form)}(s|es)?\b"
    mentions = list(re.finditer(pattern, haystack))
    if not mentions:
        return False
    for mention in mentions:
        before = haystack[max(0, mention.start() - 24) : mention.start()]
        words = re.findall(r"[a-z]+", before)[-2:]
        if not any(w in NEGATORS for w in words):
            return False  # at least one genuine mention
    return True


def _hits(term: str, haystack: str) -> bool:
    """Word-boundary match, never a bare substring, never a negated one.

    'egg' must not match 'Weekly Veggie Box'. Substring matching produced
    exactly that, and a shopper asking for eggs was handed a vegetable box
    with no indication anything had gone wrong.
    """
    for form in _forms(term):
        if not form:
            continue
        if re.search(rf"\b{re.escape(form)}(s|es)?\b", haystack) and not _negated(form, haystack):
            return True
    return False


def query_terms(text: str) -> list[str]:
    """The meaningful nouns in a free-text query."""
    words = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split()
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def find_relevant(
    products: list[Product],
    *,
    items: list[str] | None = None,
    query: str = "",
    category: str | None = None,
) -> list[Match]:
    """Candidates that genuinely answer the request, best-grounded first.

    Named items beat a free-text query, and a query beats a bare category.
    Falling all the way through to "everything in the shop" is not one of the
    options.

    When the request named specific items, failing to find them is the
    answer. Widening to the category instead turned "I want to make pasta"
    into "here is the nicest thing in the grocery aisle" -- a narrower version
    of the same guess, and just as wrong.
    """
    in_stock = [p for p in products if p.in_stock]

    named = [t for t in (items or []) if t and t.strip()]
    terms = named or query_terms(query)

    if terms:
        matches: list[Match] = []
        for product in in_stock:
            # Name and category are the product's own claim about itself.
            # Description is weaker evidence, and for synced rows it is partly
            # machine-written -- the sync tags each row with the term it was
            # found under, which is what let a ketchup answer to "onion".
            title = f"{product.name} {product.category}".lower()
            body = (product.description or "").lower()

            in_title = [t for t in terms if _hits(t, title)]
            in_body = [t for t in terms if t not in in_title and _hits(t, body)]
            hit = in_title + in_body
            if hit:
                matches.append(
                    Match(product=product, matched=hit, strength=len(in_title) * 10 + len(in_body))
                )
        if matches:
            # A product that names what was asked for beats one that merely
            # mentions it, and answering more of the request beats both.
            #
            # Ties break toward the shorter name. "Freshbury Onion" and
            # "Garden Onion Pakoda Namkeen" both name an onion, but the extra
            # nouns in the second are the product being something else that
            # happens to contain one. Brevity is a crude proxy for "the item
            # IS this", and a crude proxy beats catalog insertion order.
            matches.sort(key=lambda m: (m.strength, -len(m.product.name)), reverse=True)
            return matches
        if named:
            # Specific things were asked for and we stock none of them.
            return []

    # Nothing was named. A category on its own is still a real constraint, so
    # honour it -- but only the category, never the whole shop.
    if category:
        scoped = [p for p in in_stock if p.category == category]
        if scoped:
            return [Match(product=p, matched=[category]) for p in scoped]

    return []


def unmatched_items(items: list[str], matches: list[Match]) -> list[str]:
    """Requested items the catalog could not answer at all.

    Reported back to the shopper verbatim: being told 'no pasta' is useful,
    being handed a substitute for it without being told is not.
    """
    answered = {m.lower() for match in matches for m in match.matched}
    return [item for item in items if item.lower() not in answered]
