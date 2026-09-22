"""Deterministic hashing for user identity fields stored in Cosmos."""

from __future__ import annotations

import hashlib
import hmac


def hash_identity(secret: str, value: str) -> str:
    """HMAC-SHA256 hex digest. The same input always produces the same stored value."""

    return hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
