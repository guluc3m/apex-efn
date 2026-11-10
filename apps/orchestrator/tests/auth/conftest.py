"""Fixtures for the authentication tests: a real RSA key pair, a mocked JWKS and a fake clock.

No network and no sleeps: the JWKS is served by ``httpx.MockTransport`` and time comes from ``FakeClock``
and the explicit ``now`` passed to ``verify_access_token``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apex.auth.jwks import JwksProvider
from apex.auth.settings import AuthSettings
from tests.auth.helpers import AUDIENCE, ISSUER, KID, NOW, jwk


class FakeClock:
    """Monotonic clock under test control."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _private_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def private_pem(signing_key: rsa.RSAPrivateKey) -> bytes:
    return _private_pem(signing_key)


@pytest.fixture(scope="session")
def other_pem(other_key: rsa.RSAPrivateKey) -> bytes:
    return _private_pem(other_key)


@pytest.fixture(scope="session")
def public_pem(signing_key: rsa.RSAPrivateKey) -> bytes:
    return _public_pem(signing_key)


@pytest.fixture(scope="session")
def jwks(signing_key: rsa.RSAPrivateKey) -> dict[str, object]:
    return {"keys": [jwk(signing_key, KID)]}


@pytest.fixture
def settings() -> AuthSettings:
    return AuthSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url=f"{ISSUER}/protocol/openid-connect/certs",
        clock_skew_seconds=0,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def jwks_calls() -> list[str]:
    return []


@pytest.fixture
def provider(
    settings: AuthSettings,
    jwks: dict[str, object],
    clock: FakeClock,
    jwks_calls: list[str],
) -> JwksProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        jwks_calls.append(str(request.url))
        return httpx.Response(200, json=jwks)

    return JwksProvider(settings, transport=httpx.MockTransport(handler), clock=clock)


@pytest.fixture
def base_claims() -> dict[str, object]:
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-1",
        "tenant_id": "tenant-a",
        "roles": ["owner"],
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "auth_time": int((NOW - timedelta(minutes=1)).timestamp()),
    }


@pytest.fixture
def make_token(private_pem: bytes, base_claims: dict[str, object]) -> Callable[..., str]:
    """Build a signed access token. Overrides let a test break exactly one thing."""

    def make(
        *,
        claims: dict[str, object] | None = None,
        kid: str | None = KID,
        key: bytes | None = None,
        algorithm: str = "RS256",
        typ: str = "JWT",
    ) -> str:
        payload = dict(base_claims)
        if claims:
            payload.update(claims)
        headers: dict[str, object] = {"typ": typ}
        if kid is not None:
            headers["kid"] = kid
        return jwt.encode(payload, key or private_pem, algorithm=algorithm, headers=headers)

    return make


@pytest.fixture
def make_request() -> Callable[[dict[str, str]], object]:
    from starlette.requests import Request

    def make(headers: dict[str, str]) -> Request:
        raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
        return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})

    return make
