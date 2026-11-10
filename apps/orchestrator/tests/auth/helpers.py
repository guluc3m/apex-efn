"""Constants shared by the authentication tests."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
KID = "test-key-1"
ISSUER = "https://idp.test/realms/apex"
AUDIENCE = "apex-orchestrator"


def b64(value: dict[str, object]) -> str:
    """base64url without padding, for hand-built JOSE headers and payloads."""
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwk(key, kid: str, *, use: str = "sig", kty: str = "RSA") -> dict[str, object]:
    """A JWKS entry for an RSA key, with the fields Keycloak publishes."""
    import json

    import jwt

    entry = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    entry.update({"kid": kid, "use": use, "alg": "RS256", "kty": kty})
    return entry
