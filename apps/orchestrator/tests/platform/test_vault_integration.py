"""Integration tests against a real Vault (dev server, bootstrapped by infra/vault/init.sh).

Skipped unless VAULT_INTEGRATION_ADDR is set. Run with:
    VAULT_INTEGRATION_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=apex-dev-root-token \
        uv run pytest -q -m integration -o markers=integration
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from apex.platform.vault import VaultClient, VaultError, VaultNotFoundError

ADDR = os.environ.get("VAULT_INTEGRATION_ADDR")
ROOT_TOKEN = os.environ.get("VAULT_INTEGRATION_TOKEN") or os.environ.get("VAULT_TOKEN", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not ADDR, reason="set VAULT_INTEGRATION_ADDR to run against a real Vault"),
]


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def _tenant() -> str:
    return f"tenant-it-{_unique()}"


@pytest.fixture
async def root() -> AsyncIterator[VaultClient]:
    assert ADDR is not None
    client = VaultClient(ADDR, ROOT_TOKEN)
    yield client
    await client.aclose()


async def _policy_token(policies: list[str]) -> str:
    """Creates a child token with the given policies, using the root token. Returns the client token."""
    assert ADDR is not None
    async with httpx.AsyncClient(base_url=ADDR, headers={"X-Vault-Token": ROOT_TOKEN}) as http:
        response = await http.post(
            "/v1/auth/token/create",
            json={"policies": policies, "ttl": "10m", "no_default_policy": False},
        )
        response.raise_for_status()
        token: str = response.json()["auth"]["client_token"]
        return token


async def test_credential_round_trip(root: VaultClient) -> None:
    tenant = _tenant()
    ref = await root.put_credential(tenant, {"username": "buyer", "password": "it-secret-1"})

    payload = await root.get_credential(tenant, ref)
    assert payload.reveal() == {"username": "buyer", "password": "it-secret-1"}
    assert "it-secret-1" not in repr(payload)

    await root.delete_credential(tenant, ref)
    with pytest.raises(VaultNotFoundError):
        await root.get_credential(tenant, ref)


async def test_session_state_round_trip(root: VaultClient) -> None:
    tenant = _tenant()
    state = {"cookies": [{"name": "sid", "value": "it-cookie-2"}], "origin": "https://example.test"}

    await root.put_session_state(tenant, "acct-1", state)
    payload = await root.get_session_state(tenant, "acct-1")
    assert payload.reveal() == state

    await root.put_session_state(tenant, "acct-1", {"cookies": []})
    assert (await root.get_session_state(tenant, "acct-1")).reveal() == {"cookies": []}


async def test_ed25519_sign_and_verify_with_independent_check(root: VaultClient) -> None:
    key = f"it-{_unique()}"
    await root.ensure_signing_key(key)
    await root.ensure_signing_key(key)

    public = await root.get_public_key(key)
    assert public.version == 1
    assert len(public.raw) == 32

    data = b'{"decision":"follow","amount_minor":12345,"currency":"EUR"}'
    signature = await root.sign(key, data)
    assert signature.vault_signature.startswith("vault:v1:")
    assert len(signature.raw) == 64

    assert await root.verify(key, data, signature) is True
    assert await root.verify(key, data + b" ", signature) is False

    verifier = Ed25519PublicKey.from_public_bytes(public.raw)
    verifier.verify(signature.raw, data)
    with pytest.raises(InvalidSignature):
        verifier.verify(signature.raw, data + b" ")


async def test_signing_key_is_not_exportable(root: VaultClient) -> None:
    assert ADDR is not None
    key = f"it-{_unique()}"
    await root.ensure_signing_key(key)
    async with httpx.AsyncClient(base_url=ADDR, headers={"X-Vault-Token": ROOT_TOKEN}) as http:
        info = await http.get(f"/v1/transit/keys/{key}")
    assert info.json()["data"]["exportable"] is False
    assert info.json()["data"]["type"] == "ed25519"


async def test_browser_worker_policy_reads_credentials_but_cannot_sign(root: VaultClient) -> None:
    assert ADDR is not None
    tenant = _tenant()
    ref = await root.put_credential(tenant, {"password": "it-secret-3"})
    key = f"it-{_unique()}"
    await root.ensure_signing_key(key)

    worker_token = await _policy_token(["browser-worker"])
    worker = VaultClient(ADDR, worker_token)
    try:
        assert (await worker.get_credential(tenant, ref)).reveal() == {"password": "it-secret-3"}

        await worker.put_session_state(tenant, "acct-w", {"cookies": []})
        assert (await worker.get_session_state(tenant, "acct-w")).reveal() == {"cookies": []}

        with pytest.raises(VaultError) as sign_denied:
            await worker.sign(key, b"forged decision")
        assert sign_denied.value.status_code == 403

        with pytest.raises(VaultError) as write_denied:
            await worker.put_credential(tenant, {"password": "it-overwrite"})
        assert write_denied.value.status_code == 403
    finally:
        await worker.aclose()


async def test_orchestrator_policy_signs_but_cannot_read_credential_values(
    root: VaultClient,
) -> None:
    assert ADDR is not None
    tenant = _tenant()
    ref = await root.put_credential(tenant, {"password": "it-secret-4"})
    key = f"it-{_unique()}"
    await root.ensure_signing_key(key)

    orchestrator_token = await _policy_token(["orchestrator"])
    orchestrator = VaultClient(ADDR, orchestrator_token)
    try:
        signature = await orchestrator.sign(key, b"decision")
        assert await orchestrator.verify(key, b"decision", signature) is True

        with pytest.raises(VaultError) as read_denied:
            await orchestrator.get_credential(tenant, ref)
        assert read_denied.value.status_code == 403

        with pytest.raises(VaultError) as session_denied:
            await orchestrator.get_session_state(tenant, "acct-x")
        assert session_denied.value.status_code == 403
    finally:
        await orchestrator.aclose()
