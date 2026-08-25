"""Agent credentials.

An agent proves who it is with a bearer token. Only the SHA-256 hash is
stored, so a leaked database does not hand over working credentials, and the
raw token is returned exactly once at creation.

This is what turns "Agent Identity" from a comment into a check: the caller's
token decides which agent is acting, so the agent_id in a request body is
just a claim to be verified, never an identity to be trusted.
"""

import hashlib
import secrets

TOKEN_PREFIX = "vla"


def generate_agent_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). The raw token is never persisted."""
    raw = f"{TOKEN_PREFIX}_{secrets.token_hex(24)}"
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode()).hexdigest()
