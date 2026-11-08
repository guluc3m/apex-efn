from __future__ import annotations

import base64
import json
import logging
import pickle
from typing import Any

import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from apex.platform.vault import (
    CredentialRef,
    InvalidIdentifierError,
    SecretPayload,
    VaultClient,
    VaultError,
    VaultNotFoundError,
)

TOKEN = "s.unit-test-token-do-not-leak"
SECRET_VALUE = "super-secret-cookie-value-123"
REF = "cred_AAAAAAAAAAAAAAAAAAAAAA"


class FakeVault:
    """Minimal in-memory Vault for KV v2 and Transit. Signs with real ed25519 keys."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.kv: dict[str, dict[str, Any]] = {}
        self.keys: dict[str, Any] = {}
        self.forced: list[httpx.Response] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("X-Vault-Token") != TOKEN:
            return httpx.Response(403, json={"errors": ["permission denied"]})
        if self.forced:
            return self.forced.pop(0)
        path = request.url.path
        method = request.method
        if path.startswith("/v1/apex-kv/data/"):
            return self._kv_data(method, path.removeprefix("/v1/apex-kv/data/"), request)
        if path.startswith("/v1/apex-kv/metadata/") and method == "DELETE":
            rel = path.removeprefix("/v1/apex-kv/metadata/")
            if rel not in self.kv:
                return httpx.Response(404, json={"errors": []})
            del self.kv[rel]
            return httpx.Response(204)
        if path.startswith("/v1/transit/keys/"):
            return self._transit_keys(method, path.removeprefix("/v1/transit/keys/"), request)
        if path.startswith("/v1/transit/sign/"):
            return self._sign(path.removeprefix("/v1/transit/sign/"), request)
        if path.startswith("/v1/transit/verify/"):
            return self._verify(path.removeprefix("/v1/transit/verify/"), request)
        return httpx.Response(404, json={"errors": []})

    def _kv_data(self, method: str, rel: str, request: httpx.Request) -> httpx.Response:
        if method == "POST":
            self.kv[rel] = json.loads(request.content)["data"]
            return httpx.Response(200, json={"data": {"version": 1}})
        if method == "GET":
            if rel not in self.kv:
                return httpx.Response(404, json={"errors": []})
            return httpx.Response(200, json={"data": {"data": self.kv[rel], "metadata": {}}})
        return httpx.Response(405)

    def _transit_keys(self, method: str, name: str, request: httpx.Request) -> httpx.Response:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        if method == "POST":
            if name in self.keys:
                return httpx.Response(400, json={"errors": ["key already exists"]})
            body = json.loads(request.content)
            assert body == {"type": "ed25519", "exportable": False}
            self.keys[name] = Ed25519PrivateKey.generate()
            return httpx.Response(204)
        if method == "GET":
            if name not in self.keys:
                return httpx.Response(404, json={"errors": []})
            raw = self.keys[name].public_key().public_bytes_raw()
            return httpx.Response(
                200,
                json={
                    "data": {
                        "type": "ed25519",
                        "exportable": False,
                        "latest_version": 1,
                        "keys": {"1": {"public_key": base64.b64encode(raw).decode()}},
                    }
                },
            )
        return httpx.Response(405)

    def _sign(self, name: str, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        data = base64.b64decode(body["input"])
        signature = self.keys[name].sign(data)
        encoded = base64.b64encode(signature).decode()
        return httpx.Response(200, json={"data": {"signature": f"vault:v1:{encoded}"}})

    def _verify(self, name: str, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        data = base64.b64decode(body["input"])
        _, _, encoded = body["signature"].split(":", 2)
        signature = base64.b64decode(encoded)
        public_key = self.keys[name].public_key()
        try:
            public_key.verify(signature, data)
            valid = True
        except InvalidSignature:
            valid = False
        return httpx.Response(200, json={"data": {"valid": valid}})


@pytest.fixture
def fake() -> FakeVault:
    return FakeVault()


@pytest.fixture
def client(fake: FakeVault) -> VaultClient:
    return VaultClient(
        "http://vault.test:8200",
        TOKEN,
        transport=httpx.MockTransport(fake.handler),
        ref_token_source=lambda: "AAAAAAAAAAAAAAAAAAAAAA",
    )


def test_credential_ref_accepts_generated_format() -> None:
    assert str(CredentialRef(REF)) == REF


@pytest.mark.parametrize(
    "value",
    [
        "../../etc/passwd",
        "cred_../x",
        "cred_a/b",
        "cred_short",
        f"{REF}\n",
        "cred_" + "A" * 65,
        "",
    ],
)
def test_credential_ref_rejects_path_like_values(value: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        CredentialRef(value)


@pytest.mark.parametrize("tenant", ["../tenant-b", "tenant/a", "", "Tenant-A", "tenant-a\n", ".."])
async def test_invalid_tenant_is_rejected_before_any_request(
    client: VaultClient, fake: FakeVault, tenant: str
) -> None:
    with pytest.raises(InvalidIdentifierError):
        await client.get_credential(tenant, REF)
    with pytest.raises(InvalidIdentifierError):
        await client.put_credential(tenant, {"k": "v"})
    assert fake.requests == []


@pytest.mark.parametrize("account", ["../x", "a/b", "", ".hidden", "acc\n"])
async def test_invalid_account_is_rejected_before_any_request(
    client: VaultClient, fake: FakeVault, account: str
) -> None:
    with pytest.raises(InvalidIdentifierError):
        await client.get_session_state("tenant-a", account)
    assert fake.requests == []


async def test_put_then_get_credential_round_trip(client: VaultClient, fake: FakeVault) -> None:
    ref = await client.put_credential("tenant-a", {"username": "buyer", "password": SECRET_VALUE})

    assert str(ref) == REF
    assert fake.requests[-1].method == "POST"
    assert fake.requests[-1].url.path == f"/v1/apex-kv/data/tenants/tenant-a/credentials/{REF}"
    assert json.loads(fake.requests[-1].content) == {
        "data": {"username": "buyer", "password": SECRET_VALUE}
    }

    payload = await client.get_credential("tenant-a", ref)
    assert payload.reveal() == {"username": "buyer", "password": SECRET_VALUE}


async def test_default_ref_generator_yields_valid_refs(fake: FakeVault) -> None:
    client = VaultClient("http://vault.test", TOKEN, transport=httpx.MockTransport(fake.handler))
    ref = await client.put_credential("tenant-a", {"k": "v"})
    assert ref.value.startswith("cred_")
    await client.aclose()


async def test_get_missing_credential_raises_not_found(client: VaultClient) -> None:
    with pytest.raises(VaultNotFoundError):
        await client.get_credential("tenant-a", REF)


async def test_delete_credential_uses_metadata_path_and_is_idempotent(
    client: VaultClient, fake: FakeVault
) -> None:
    ref = await client.put_credential("tenant-a", {"k": "v"})
    await client.delete_credential("tenant-a", ref)
    assert fake.requests[-1].method == "DELETE"
    assert fake.requests[-1].url.path == f"/v1/apex-kv/metadata/tenants/tenant-a/credentials/{ref}"
    await client.delete_credential("tenant-a", ref)
    with pytest.raises(VaultNotFoundError):
        await client.get_credential("tenant-a", ref)


async def test_session_state_round_trip_uses_browser_sessions_path(
    client: VaultClient, fake: FakeVault
) -> None:
    state = {"cookies": [{"name": "sid", "value": SECRET_VALUE}]}
    await client.put_session_state("tenant-a", "acct-1", state)

    assert fake.requests[-1].url.path == "/v1/apex-kv/data/tenants/tenant-a/browser-sessions/acct-1"
    payload = await client.get_session_state("tenant-a", "acct-1")
    assert payload.reveal() == state


async def test_session_state_is_isolated_per_tenant(client: VaultClient) -> None:
    await client.put_session_state("tenant-a", "acct-1", {"k": "v"})
    with pytest.raises(VaultNotFoundError):
        await client.get_session_state("tenant-b", "acct-1")


async def test_secret_values_never_appear_in_repr_str_format_or_logs(
    client: VaultClient, caplog: pytest.LogCaptureFixture
) -> None:
    await client.put_session_state("tenant-a", "acct-1", {"password": SECRET_VALUE})
    caplog.set_level(logging.DEBUG)
    payload = await client.get_session_state("tenant-a", "acct-1")

    assert SECRET_VALUE not in repr(payload)
    assert SECRET_VALUE not in str(payload)
    assert SECRET_VALUE not in f"{payload}"
    assert SECRET_VALUE not in f"{payload!r}"
    assert SECRET_VALUE not in repr([payload])

    logging.getLogger("apex.test").warning("payload=%s extra=%r", payload, payload)
    logging.getLogger("apex.test").info("object", extra={"payload": payload})
    assert SECRET_VALUE not in caplog.text
    for record in caplog.records:
        assert SECRET_VALUE not in record.getMessage()
        assert SECRET_VALUE not in str(record.__dict__.get("payload", ""))


async def test_secret_payload_cannot_be_serialised_or_pickled() -> None:
    payload = SecretPayload({"password": SECRET_VALUE})
    with pytest.raises(TypeError):
        json.dumps(payload)
    with pytest.raises(TypeError):
        pickle.dumps(payload)


async def test_error_messages_hide_token_and_payload(fake: FakeVault) -> None:
    client = VaultClient("http://vault.test", TOKEN, transport=httpx.MockTransport(fake.handler))
    fake.forced.append(
        httpx.Response(500, json={"errors": [f"boom {SECRET_VALUE} {TOKEN}"]}),
    )
    with pytest.raises(VaultError) as excinfo:
        await client.put_credential("tenant-a", {"password": SECRET_VALUE})
    message = str(excinfo.value)
    assert SECRET_VALUE not in message
    assert TOKEN not in message
    assert excinfo.value.status_code == 500
    assert excinfo.value.operation == "put_credential"
    await client.aclose()


async def test_wrong_token_is_rejected_without_leaking_it(fake: FakeVault) -> None:
    client = VaultClient(
        "http://vault.test", "s.wrong", transport=httpx.MockTransport(fake.handler)
    )
    with pytest.raises(VaultError, match="HTTP 403") as excinfo:
        await client.get_credential("tenant-a", REF)
    assert "s.wrong" not in str(excinfo.value)
    await client.aclose()


async def test_transport_error_is_wrapped_without_chaining_details() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused {TOKEN}", request=request)

    client = VaultClient("http://vault.test", TOKEN, transport=httpx.MockTransport(refuse))
    with pytest.raises(VaultError, match="transport error") as excinfo:
        await client.get_credential("tenant-a", REF)
    assert TOKEN not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    await client.aclose()


async def test_client_repr_hides_token(client: VaultClient) -> None:
    assert TOKEN not in repr(client)
    assert "<redacted>" in repr(client)


async def test_from_env_requires_addr_and_token() -> None:
    with pytest.raises(VaultError):
        VaultClient.from_env({"VAULT_ADDR": "http://vault.test"})
    with pytest.raises(VaultError):
        VaultClient.from_env({"VAULT_TOKEN": TOKEN})


async def test_from_env_builds_client_from_environment() -> None:
    env = {"VAULT_ADDR": "http://vault.test:8200", "VAULT_TOKEN": TOKEN}
    client = VaultClient.from_env(env)
    assert client is not None
    await client.aclose()


async def test_ensure_signing_key_creates_non_exportable_ed25519_key(
    client: VaultClient, fake: FakeVault
) -> None:
    await client.ensure_signing_key("gate-agent")
    posts = [r for r in fake.requests if r.method == "POST" and "/keys/" in r.url.path]
    assert len(posts) == 1
    assert posts[0].url.path == "/v1/transit/keys/gate-agent"
    assert json.loads(posts[0].content) == {"type": "ed25519", "exportable": False}


async def test_ensure_signing_key_is_idempotent(client: VaultClient, fake: FakeVault) -> None:
    await client.ensure_signing_key("gate-agent")
    count = len(fake.requests)
    await client.ensure_signing_key("gate-agent")
    assert [r.method for r in fake.requests[count:]] == ["GET", "GET"]


async def test_ensure_signing_key_tolerates_concurrent_creation(
    client: VaultClient, fake: FakeVault
) -> None:
    await client.ensure_signing_key("orchestrator")
    fake.forced.append(httpx.Response(404, json={"errors": []}))
    fake.forced.append(httpx.Response(400, json={"errors": ["key already exists"]}))
    await client.ensure_signing_key("orchestrator")


async def test_ensure_signing_key_rejects_invalid_names(
    client: VaultClient, fake: FakeVault
) -> None:
    for name in ["../x", "Gate", "a/b", "x"]:
        with pytest.raises(InvalidIdentifierError):
            await client.ensure_signing_key(name)
    assert fake.requests == []


async def test_get_public_key_returns_raw_32_bytes(client: VaultClient) -> None:
    await client.ensure_signing_key("orchestrator")
    key = await client.get_public_key("orchestrator")
    assert key.version == 1
    assert len(key.raw) == 32
    Ed25519PublicKey.from_public_bytes(key.raw)


async def test_get_public_key_missing_key_raises(client: VaultClient) -> None:
    with pytest.raises(VaultNotFoundError):
        await client.get_public_key("orchestrator")


async def test_sign_sends_base64_input_and_returns_vault_and_raw_forms(
    client: VaultClient, fake: FakeVault
) -> None:
    await client.ensure_signing_key("orchestrator")
    data = b'{"decision":"follow","amount_minor":12345}'
    signature = await client.sign("orchestrator", data)

    sign_request = fake.requests[-1]
    assert sign_request.url.path == "/v1/transit/sign/orchestrator"
    assert json.loads(sign_request.content) == {"input": base64.b64encode(data).decode()}

    assert signature.vault_signature.startswith("vault:v1:")
    assert signature.key_version == 1
    assert len(signature.raw) == 64
    assert signature.signature_b64 == base64.b64encode(signature.raw).decode()


async def test_signature_verifies_independently_with_cryptography(client: VaultClient) -> None:
    await client.ensure_signing_key("orchestrator")
    data = b"canonical payload"
    signature = await client.sign("orchestrator", data)
    public_key = await client.get_public_key("orchestrator")

    Ed25519PublicKey.from_public_bytes(public_key.raw).verify(signature.raw, data)


async def test_verify_true_for_valid_and_false_for_tampered_data(
    client: VaultClient, fake: FakeVault
) -> None:
    await client.ensure_signing_key("orchestrator")
    data = b"score=0.91"
    signature = await client.sign("orchestrator", data)

    assert await client.verify("orchestrator", data, signature) is True
    assert await client.verify("orchestrator", b"score=0.92", signature) is False
    assert await client.verify("orchestrator", data, signature.vault_signature) is True
    tampered_body = {
        "input": base64.b64encode(b"score=0.92").decode(),
        "signature": signature.vault_signature,
    }
    bodies = [
        json.loads(r.content) for r in fake.requests if r.url.path.endswith("/verify/orchestrator")
    ]
    assert tampered_body in bodies


async def test_verify_rejects_malformed_signature_without_request(
    client: VaultClient, fake: FakeVault
) -> None:
    before = len(fake.requests)
    with pytest.raises(InvalidIdentifierError):
        await client.verify("orchestrator", b"x", "not-a-vault-signature")
    assert len(fake.requests) == before


async def test_sign_rejects_unexpected_response_shape(client: VaultClient, fake: FakeVault) -> None:
    await client.ensure_signing_key("orchestrator")
    fake.forced.append(httpx.Response(200, json={"data": {"signature": "garbage"}}))
    with pytest.raises(VaultError, match="unexpected signature format"):
        await client.sign("orchestrator", b"x")


async def test_client_exposes_no_export_operation() -> None:
    names = [name for name in dir(VaultClient) if not name.startswith("__")]
    assert not [name for name in names if "export" in name.lower()]


async def test_token_is_sent_as_header_only(client: VaultClient, fake: FakeVault) -> None:
    with pytest.raises(VaultNotFoundError):
        await client.get_credential("tenant-a", REF)
    request = fake.requests[-1]
    assert request.headers["X-Vault-Token"] == TOKEN
    assert TOKEN not in str(request.url)
