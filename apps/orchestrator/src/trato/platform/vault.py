"""Vault client for the orchestrator: KV v2 (credentials, browser session state) and Transit (ed25519).

Rules (AGENTS.md section 3.8, PROMPT-IMPLEMENTACION.md 3.1):
- Marketplace credentials are referenced only by `CredentialRef`. Their values are read by trusted backend
  code and never returned to the LLM or the browser.
- Transit keys are created with `exportable=false`. This client has no operation that exports key material.
- Errors never include payload values, the token or Vault's response body.
"""

from __future__ import annotations

import base64
import os
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Self

import httpx
from pydantic import BaseModel, SecretStr

KV_MOUNT: Final = "trato-kv"
TRANSIT_MOUNT: Final = "transit"

_TENANT_RE: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_ACCOUNT_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_REF_RE: Final = re.compile(r"cred_[A-Za-z0-9_-]{16,64}")
_KEY_NAME_RE: Final = re.compile(r"[a-z][a-z0-9-]{1,62}")
_VAULT_SIGNATURE_RE: Final = re.compile(r"vault:v([0-9]+):([A-Za-z0-9+/]+={0,2})")
_ED25519_PUBLIC_KEY_LEN: Final = 32

RefTokenSource = Callable[[], str]


def _random_ref_token() -> str:
    return secrets.token_urlsafe(16)


class InvalidIdentifierError(ValueError):
    """An identifier does not match its strict format. The offending value is not echoed back."""


class VaultError(Exception):
    """Vault request failed. The message holds only the operation name and the HTTP status."""

    def __init__(self, operation: str, status_code: int | None, detail: str = "") -> None:
        self.operation = operation
        self.status_code = status_code
        message = f"Vault {operation} failed"
        if status_code is not None:
            message += f" (HTTP {status_code})"
        if detail:
            message += f": {detail}"
        super().__init__(message)


class VaultNotFoundError(VaultError):
    """The requested KV path or Transit key does not exist."""


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """Opaque pointer to a marketplace credential stored in Vault KV. Carries no secret material."""

    value: str

    def __post_init__(self) -> None:
        if _REF_RE.fullmatch(self.value) is None:
            raise InvalidIdentifierError("invalid credential reference")

    def __str__(self) -> str:
        return self.value


class SecretPayload:
    """Values read from Vault. Redacted in repr, str and format, and not serialisable.

    Call `reveal()` only in trusted backend code that consumes the values. Never log or serialise the result.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data: dict[str, Any] = dict(data)

    def reveal(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return "SecretPayload(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    def __format__(self, format_spec: str) -> str:
        return "<redacted>"

    def __reduce__(self) -> str:
        raise TypeError("SecretPayload cannot be pickled")


@dataclass(frozen=True, slots=True)
class TransitPublicKey:
    name: str
    version: int
    raw: bytes


@dataclass(frozen=True, slots=True)
class TransitSignature:
    key_name: str
    key_version: int
    vault_signature: str
    signature_b64: str

    @property
    def raw(self) -> bytes:
        return base64.b64decode(self.signature_b64)


class _KvReadData(BaseModel):
    data: dict[str, Any]


class _KvReadBody(BaseModel):
    data: _KvReadData


class _TransitKeyVersion(BaseModel):
    public_key: str | None = None


class _TransitKeyInfo(BaseModel):
    type: str
    exportable: bool
    latest_version: int
    keys: dict[str, _TransitKeyVersion]


class _TransitKeyBody(BaseModel):
    data: _TransitKeyInfo


class _TransitSignData(BaseModel):
    signature: str


class _TransitSignBody(BaseModel):
    data: _TransitSignData


class _TransitVerifyData(BaseModel):
    valid: bool


class _TransitVerifyBody(BaseModel):
    data: _TransitVerifyData


def _tenant(tenant_id: str) -> str:
    if _TENANT_RE.fullmatch(tenant_id) is None:
        raise InvalidIdentifierError("invalid tenant_id")
    return tenant_id


def _account(account_id: str) -> str:
    if _ACCOUNT_RE.fullmatch(account_id) is None:
        raise InvalidIdentifierError("invalid account_id")
    return account_id


def _key_name(name: str) -> str:
    if _KEY_NAME_RE.fullmatch(name) is None:
        raise InvalidIdentifierError("invalid transit key name")
    return name


def _ref(ref: CredentialRef | str) -> CredentialRef:
    return ref if isinstance(ref, CredentialRef) else CredentialRef(ref)


class VaultClient:
    """Async Vault client over HTTP. Use as an async context manager or call `aclose()`."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
        ref_token_source: RefTokenSource = _random_ref_token,
    ) -> None:
        self._token = SecretStr(token)
        self._ref_token_source = ref_token_source
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Vault-Token": token},
            transport=transport,
            timeout=timeout,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        source = os.environ if env is None else env
        addr = source.get("VAULT_ADDR")
        token = source.get("VAULT_TOKEN")
        if not addr or not token:
            raise VaultError("configure", None, "VAULT_ADDR and VAULT_TOKEN must be set")
        return cls(addr, token)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"VaultClient(base_url={self._http.base_url!s}, token=<redacted>)"

    async def _request(
        self,
        operation: str,
        method: str,
        path: str,
        json: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(method, path, json=json)
        except httpx.HTTPError:
            raise VaultError(operation, None, "transport error") from None
        if response.status_code == 404:
            raise VaultNotFoundError(operation, 404)
        if response.status_code >= 400:
            raise VaultError(operation, response.status_code)
        return response

    async def _kv_write(self, operation: str, rel_path: str, payload: Mapping[str, Any]) -> None:
        await self._request(
            operation, "POST", f"/v1/{KV_MOUNT}/data/{rel_path}", json={"data": dict(payload)}
        )

    async def _kv_read(self, operation: str, rel_path: str) -> SecretPayload:
        response = await self._request(operation, "GET", f"/v1/{KV_MOUNT}/data/{rel_path}")
        try:
            body = _KvReadBody.model_validate_json(response.content)
        except ValueError:
            raise VaultError(operation, response.status_code, "unexpected response") from None
        return SecretPayload(body.data.data)

    async def _kv_delete(self, operation: str, rel_path: str) -> None:
        try:
            await self._request(operation, "DELETE", f"/v1/{KV_MOUNT}/metadata/{rel_path}")
        except VaultNotFoundError:
            return

    async def put_credential(self, tenant_id: str, payload: Mapping[str, Any]) -> CredentialRef:
        tenant = _tenant(tenant_id)
        ref = CredentialRef(f"cred_{self._ref_token_source()}")
        await self._kv_write("put_credential", f"tenants/{tenant}/credentials/{ref}", payload)
        return ref

    async def get_credential(self, tenant_id: str, ref: CredentialRef | str) -> SecretPayload:
        tenant = _tenant(tenant_id)
        return await self._kv_read("get_credential", f"tenants/{tenant}/credentials/{_ref(ref)}")

    async def delete_credential(self, tenant_id: str, ref: CredentialRef | str) -> None:
        """Removes every version of the credential. Deleting a missing credential is a no-op."""
        tenant = _tenant(tenant_id)
        await self._kv_delete("delete_credential", f"tenants/{tenant}/credentials/{_ref(ref)}")

    async def put_session_state(
        self, tenant_id: str, account_id: str, state: Mapping[str, Any]
    ) -> None:
        tenant = _tenant(tenant_id)
        account = _account(account_id)
        await self._kv_write(
            "put_session_state", f"tenants/{tenant}/browser-sessions/{account}", state
        )

    async def get_session_state(self, tenant_id: str, account_id: str) -> SecretPayload:
        tenant = _tenant(tenant_id)
        account = _account(account_id)
        return await self._kv_read(
            "get_session_state", f"tenants/{tenant}/browser-sessions/{account}"
        )

    async def ensure_signing_key(self, name: str) -> None:
        """Creates a non-exportable ed25519 Transit key if it is missing. Fails if the type differs."""
        key = _key_name(name)
        if await self._read_key_info("ensure_signing_key", key) is None:
            try:
                await self._request(
                    "ensure_signing_key",
                    "POST",
                    f"/v1/{TRANSIT_MOUNT}/keys/{key}",
                    json={"type": "ed25519", "exportable": False},
                )
            except VaultError:
                if await self._read_key_info("ensure_signing_key", key) is None:
                    raise
        info = await self._read_key_info("ensure_signing_key", key)
        if info is None:
            raise VaultError("ensure_signing_key", None, "key missing after creation")
        if info.type != "ed25519" or info.exportable:
            raise VaultError(
                "ensure_signing_key", None, "existing key is not a non-exportable ed25519 key"
            )

    async def _read_key_info(self, operation: str, key: str) -> _TransitKeyInfo | None:
        try:
            response = await self._request(operation, "GET", f"/v1/{TRANSIT_MOUNT}/keys/{key}")
        except VaultNotFoundError:
            return None
        try:
            return _TransitKeyBody.model_validate_json(response.content).data
        except ValueError:
            raise VaultError(operation, response.status_code, "unexpected response") from None

    async def get_public_key(self, name: str) -> TransitPublicKey:
        key = _key_name(name)
        info = await self._read_key_info("get_public_key", key)
        if info is None:
            raise VaultNotFoundError("get_public_key", 404)
        encoded = info.keys.get(str(info.latest_version), _TransitKeyVersion()).public_key
        if encoded is None:
            raise VaultError("get_public_key", None, "public key missing")
        raw = base64.b64decode(encoded)
        if len(raw) != _ED25519_PUBLIC_KEY_LEN:
            raise VaultError("get_public_key", None, "unexpected public key length")
        return TransitPublicKey(name=key, version=info.latest_version, raw=raw)

    async def sign(self, name: str, data: bytes) -> TransitSignature:
        """Signs the raw bytes with ed25519 (pure, not prehashed). The payload is never logged."""
        key = _key_name(name)
        response = await self._request(
            "sign",
            "POST",
            f"/v1/{TRANSIT_MOUNT}/sign/{key}",
            json={"input": base64.b64encode(data).decode("ascii")},
        )
        try:
            signature = _TransitSignBody.model_validate_json(response.content).data.signature
        except ValueError:
            raise VaultError("sign", response.status_code, "unexpected response") from None
        match = _VAULT_SIGNATURE_RE.fullmatch(signature)
        if match is None:
            raise VaultError("sign", response.status_code, "unexpected signature format")
        return TransitSignature(
            key_name=key,
            key_version=int(match.group(1)),
            vault_signature=signature,
            signature_b64=match.group(2),
        )

    async def verify(self, name: str, data: bytes, signature: TransitSignature | str) -> bool:
        """Returns False for a signature that does not match the data. Malformed input raises VaultError."""
        key = _key_name(name)
        vault_signature = (
            signature.vault_signature if isinstance(signature, TransitSignature) else signature
        )
        if _VAULT_SIGNATURE_RE.fullmatch(vault_signature) is None:
            raise InvalidIdentifierError("invalid transit signature format")
        response = await self._request(
            "verify",
            "POST",
            f"/v1/{TRANSIT_MOUNT}/verify/{key}",
            json={
                "input": base64.b64encode(data).decode("ascii"),
                "signature": vault_signature,
            },
        )
        try:
            return _TransitVerifyBody.model_validate_json(response.content).data.valid
        except ValueError:
            raise VaultError("verify", response.status_code, "unexpected response") from None
