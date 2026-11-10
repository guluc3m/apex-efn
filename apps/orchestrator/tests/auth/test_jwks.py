"""JWKS caching, rotation and failure behaviour."""

from __future__ import annotations

import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from apex.auth.errors import UNKNOWN_KEY, AuthError, JwksError
from apex.auth.jwks import JwksProvider
from apex.auth.settings import AuthSettings
from tests.auth.helpers import AUDIENCE, ISSUER, jwk


def _provider(settings, clock, handler) -> JwksProvider:
    return JwksProvider(settings, transport=httpx.MockTransport(handler), clock=clock)


async def test_rotation_refetches_once_and_finds_the_new_key(
    settings, clock, signing_key, other_key
):
    old = {"keys": [jwk(signing_key, "k-old")]}
    new = {"keys": [jwk(other_key, "k-new")]}
    responses = [old, new]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=responses[min(len(calls) - 1, len(responses) - 1)])

    provider = _provider(settings, clock, handler)
    await provider.keys()  # warm cache with the old key set, as after a normal startup

    key = await provider.key_for("k-new")

    assert key is not None
    assert len(calls) == 2


async def test_persistent_unknown_kid_does_not_hammer_the_idp(settings, clock, jwks):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=jwks)

    provider = _provider(settings, clock, handler)

    for _ in range(5):
        with pytest.raises(AuthError) as caught:
            await provider.key_for("never-existed")
        assert caught.value.reason == UNKNOWN_KEY

    # One initial fetch plus exactly one rotation refetch; the cooldown stops the rest.
    assert len(calls) == 2


async def test_cooldown_expires_and_allows_another_refetch(settings, clock, jwks):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=jwks)

    provider = _provider(settings, clock, handler)
    await provider.keys()  # initial fetch

    with pytest.raises(AuthError):
        await provider.key_for("missing")  # one rotation refetch
    with pytest.raises(AuthError):
        await provider.key_for("missing")  # within the cooldown: no fetch
    clock.advance(settings.refetch_cooldown_seconds + 1)
    with pytest.raises(AuthError):
        await provider.key_for("missing")  # cooldown over: one more

    assert len(calls) == 3


async def test_key_set_without_usable_keys_is_rejected(settings, clock, signing_key):
    document = {"keys": [{**jwk(signing_key, "enc-key", use="enc")}]}
    provider = _provider(settings, clock, lambda request: httpx.Response(200, json=document))

    with pytest.raises(JwksError) as caught:
        await provider.keys()

    assert caught.value.reason == JwksError.NO_USABLE_KEYS


async def test_non_rsa_keys_are_ignored(settings, clock, signing_key):
    document = {
        "keys": [
            {"kty": "EC", "kid": "ec", "crv": "P-256", "x": "a", "y": "b"},
            jwk(signing_key, "sig-key"),
        ]
    }
    provider = _provider(settings, clock, lambda request: httpx.Response(200, json=document))

    keys = await provider.keys()

    assert set(keys) == {"sig-key"}


async def test_unavailable_idp_raises_jwks_unavailable(settings, clock):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    provider = _provider(settings, clock, handler)

    with pytest.raises(JwksError) as caught:
        await provider.keys()

    assert caught.value.reason == JwksError.UNAVAILABLE


async def test_stale_keys_are_kept_when_a_refresh_fails(settings, clock, jwks):
    state = {"fail": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["fail"]:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json=jwks)

    provider = _provider(settings, clock, handler)
    first = await provider.keys()
    state["fail"] = True
    clock.advance(settings.cache_ttl_seconds + 1)

    key = await provider.key_for("test-key-1")

    assert key is not None
    assert set(first) == {"test-key-1"}


async def test_invalid_document_is_rejected(settings, clock):
    provider = _provider(settings, clock, lambda request: httpx.Response(200, text=json.dumps([])))

    with pytest.raises(JwksError) as caught:
        await provider.keys()

    assert caught.value.reason == JwksError.INVALID_DOCUMENT


async def test_non_200_is_unavailable(settings, clock):
    provider = _provider(settings, clock, lambda request: httpx.Response(503))

    with pytest.raises(JwksError) as caught:
        await provider.keys()

    assert caught.value.reason == JwksError.UNAVAILABLE


async def test_settings_hash_lets_the_provider_cache_be_shared():
    # The provider cache in deps is keyed by AuthSettings, so the dataclass must stay hashable.
    a = AuthSettings(issuer=ISSUER, audience=AUDIENCE, jwks_url=f"{ISSUER}/certs")
    b = AuthSettings(issuer=ISSUER, audience=AUDIENCE, jwks_url=f"{ISSUER}/certs")

    assert a == b
    assert hash(a) == hash(b)


def test_keypair_helper_is_rsa(signing_key: rsa.RSAPrivateKey) -> None:
    assert signing_key.key_size == 2048
    assert jwk(signing_key, "k")["kty"] == "RSA"
