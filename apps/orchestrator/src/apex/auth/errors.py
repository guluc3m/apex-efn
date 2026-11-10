"""Closed error reasons for the authentication seam (D1-05).

Every reason is a constant of this module so a caller can branch on it and a test can assert it. No
message built from these values ever contains the token, the key material or an IdP response body:
those are secrets, and they must not reach logs or problem responses.
"""

from __future__ import annotations

from typing import Final

# Reasons a bearer token is refused. Closed set: anything new must be added here and documented.
MALFORMED: Final = "malformed"
BAD_SIGNATURE: Final = "bad_signature"
EXPIRED: Final = "expired"
NOT_YET_VALID: Final = "not_yet_valid"
WRONG_ISSUER: Final = "wrong_issuer"
WRONG_AUDIENCE: Final = "wrong_audience"
UNKNOWN_KEY: Final = "unknown_key"
JWKS_UNAVAILABLE: Final = "jwks_unavailable"
MISSING_CLAIM: Final = "missing_claim"
UNSUPPORTED_ALGORITHM: Final = "unsupported_algorithm"
MISSING_TOKEN: Final = "missing_token"

AUTH_REASONS: Final = frozenset(
    {
        MALFORMED,
        BAD_SIGNATURE,
        EXPIRED,
        NOT_YET_VALID,
        WRONG_ISSUER,
        WRONG_AUDIENCE,
        UNKNOWN_KEY,
        JWKS_UNAVAILABLE,
        MISSING_CLAIM,
        UNSUPPORTED_ALGORITHM,
        MISSING_TOKEN,
    }
)


class AuthError(Exception):
    """A bearer token was refused. ``reason`` is one of :data:`AUTH_REASONS`."""

    def __init__(self, reason: str, *, detail: str | None = None) -> None:
        if reason not in AUTH_REASONS:
            raise ValueError(f"unknown auth reason: {reason!r}")
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class JwksError(Exception):
    """The key set could not be used. Reasons: ``unavailable``, ``invalid_document``, ``no_usable_keys``."""

    UNAVAILABLE: Final = "unavailable"
    INVALID_DOCUMENT: Final = "invalid_document"
    NO_USABLE_KEYS: Final = "no_usable_keys"
    REASONS: Final = frozenset({UNAVAILABLE, INVALID_DOCUMENT, NO_USABLE_KEYS})

    def __init__(self, reason: str) -> None:
        if reason not in self.REASONS:
            raise ValueError(f"unknown jwks reason: {reason!r}")
        super().__init__(reason)
        self.reason = reason


__all__ = [
    "AUTH_REASONS",
    "AuthError",
    "BAD_SIGNATURE",
    "EXPIRED",
    "JWKS_UNAVAILABLE",
    "JwksError",
    "MALFORMED",
    "MISSING_CLAIM",
    "MISSING_TOKEN",
    "NOT_YET_VALID",
    "UNKNOWN_KEY",
    "UNSUPPORTED_ALGORITHM",
    "WRONG_AUDIENCE",
    "WRONG_ISSUER",
]
