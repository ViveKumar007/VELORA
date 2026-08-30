"""Password hashing and session tokens for the two human audiences.

Velora has three kinds of caller, and they authenticate differently on
purpose:

  agents    long-lived bearer token, no password, no session   (security.py)
  users     email + password -> session token                  (here)
  merchants email + password -> session token                  (here)

Users and merchants share the mechanism but never the audience: a session
token carries the kind it was issued for, and a merchant token presented to a
buyer-side endpoint is rejected. Sharing a login between the two would mean a
merchant could read a buyer's policies, which is the whole thing we are
trying to prevent.

Everything here is stdlib. A hackathon does not need a JWT library to sign
one claim, and fewer dependencies is fewer things to get wrong.
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from typing import Literal

from app.config import settings
from app.models import utcnow

TOKEN_PREFIX = "vs"
PBKDF2_ROUNDS = 200_000

SessionKind = Literal["user", "merchant"]


class AuthError(Exception):
    """Credentials were missing, malformed, expired or simply wrong."""


# --- Passwords -----------------------------------------------------------


def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 with a per-password salt.

    Stored as an algorithm-tagged string so the parameters can be raised
    later without invalidating existing hashes.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check. Returns False rather than raising on junk input."""
    try:
        algorithm, rounds, salt_hex, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


# --- Session tokens ------------------------------------------------------


def _secret() -> bytes:
    """Signing key for session tokens.

    Falls back to a per-process random value when SESSION_SECRET is unset,
    which is safe (tokens simply stop working after a restart) but means
    everyone is logged out on redeploy. Set it in production.
    """
    return (settings.session_secret or _EPHEMERAL_SECRET).encode()


_EPHEMERAL_SECRET = secrets.token_hex(32)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session(subject_id: str, kind: SessionKind, hours: int = 12) -> str:
    """Mint a signed session token for a user or a merchant."""
    payload = {
        "sub": subject_id,
        "kind": kind,
        "exp": int((utcnow() + timedelta(hours=hours)).timestamp()),
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{TOKEN_PREFIX}_{body}.{signature}"


def read_session(token: str, *, expect: SessionKind) -> str:
    """Verify a token and return the subject id it was issued for.

    Raises AuthError on anything wrong -- bad signature, wrong audience,
    expired, malformed. The caller does not get to distinguish which, because
    telling an attacker *why* a token failed is free information.
    """
    if not token or not token.startswith(f"{TOKEN_PREFIX}_"):
        raise AuthError("Not a session token.")

    try:
        body, signature = token[len(TOKEN_PREFIX) + 1 :].split(".", 1)
    except ValueError as exc:
        raise AuthError("Malformed session token.") from exc

    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AuthError("Invalid session token.")

    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Unreadable session token.") from exc

    if payload.get("kind") != expect:
        # A merchant session must never satisfy a buyer-side dependency.
        raise AuthError("This session is not valid for that area.")
    if int(payload.get("exp", 0)) < int(utcnow().timestamp()):
        raise AuthError("Session expired. Please sign in again.")

    subject = payload.get("sub")
    if not subject:
        raise AuthError("Session token has no subject.")
    return subject
