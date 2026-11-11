"""Connected accounts (issue 154): credentials go to the vault, never to the database, the response or the audit."""

from __future__ import annotations

import uuid
from typing import Any

from apex.api import accounts as accounts_api
from apex.platform.vault import VaultError
from tests.signing.test_keys import Harness, app_db, h, migrated_db, pytestmark, seeded

__all__ = ["app_db", "h", "migrated_db", "pytestmark", "seeded"]

SECRET = "hunter2-very-secret"


class FakeVault:
    def __init__(self) -> None:
        self.stored: dict[str, dict[str, Any]] = {}
        self.down = False

    async def put_credential(self, tenant_id: str, payload: Any) -> str:
        if self.down:
            raise VaultError("put_credential", 503)
        ref = f"cred_{uuid.uuid4().hex}"
        self.stored[ref] = dict(payload)
        return ref

    async def delete_credential(self, tenant_id: str, ref: Any) -> None:
        self.stored.pop(str(ref), None)


def _wire(h: Harness) -> FakeVault:
    vault = FakeVault()
    h.app.dependency_overrides[accounts_api.get_vault] = lambda: vault
    h.app.dependency_overrides[accounts_api.get_platform_ids] = lambda: ["mock-a", "mock-b"]
    h.as_user("alice", roles=("admin",))
    return vault


def _body(platform: str = "mock-a") -> dict[str, str]:
    return {"platform": platform, "username": "ana@example.test", "password": SECRET}


async def test_connect_stores_the_secret_only_in_the_vault_and_replaces_the_old_account(
    h: Harness,
) -> None:
    vault = _wire(h)
    first = await h.client.post("/v1/connected-accounts", json=_body())
    assert first.status_code == 201, first.text
    account = first.json()
    assert account["status"] == "active" and account["platform"] == "mock-a"
    assert SECRET not in first.text
    assert vault.stored[account["credential_ref"]["id"]] == {
        "username": "ana@example.test",
        "password": SECRET,
    }

    second = (await h.client.post("/v1/connected-accounts", json=_body())).json()
    assert second["id"] != account["id"]
    assert list(vault.stored) == [second["credential_ref"]["id"]]  # the old credential is gone

    listed = (await h.client.get("/v1/connected-accounts")).json()
    assert [i["id"] for i in listed["items"]] == [second["id"]]
    assert listed["platforms"] == ["mock-a", "mock-b"]
    assert SECRET not in str(listed)

    audit = (await _audit(h)).text
    assert "account.connected" in audit and SECRET not in audit and "ana@example.test" not in audit


async def _audit(h: Harness) -> Any:
    h.as_user("root", roles=("admin",))
    out = await h.client.get("/v1/audit")
    h.as_user("alice", roles=("admin",))
    return out


async def test_disconnect_deletes_the_credential_and_is_idempotent(h: Harness) -> None:
    vault = _wire(h)
    account = (await h.client.post("/v1/connected-accounts", json=_body("mock-b"))).json()
    done = await h.client.delete(f"/v1/connected-accounts/{account['id']}")
    assert (done.status_code, done.json()["status"]) == (200, "disabled")
    assert vault.stored == {}
    assert (await h.client.delete(f"/v1/connected-accounts/{account['id']}")).status_code == 200
    listed = (await h.client.get("/v1/connected-accounts")).json()["items"]
    assert account["id"] not in [i["id"] for i in listed]
    assert (await h.client.delete("/v1/connected-accounts/nope")).status_code == 404


async def test_only_owner_or_admin_unknown_platform_and_vault_down(h: Harness) -> None:
    vault = _wire(h)
    h.as_user("alice", roles=("buyer",))
    assert (await h.client.get("/v1/connected-accounts")).status_code == 403
    assert (await h.client.post("/v1/connected-accounts", json=_body())).status_code == 403

    h.as_user("alice", roles=("owner",))
    bad = await h.client.post("/v1/connected-accounts", json=_body("nope"))
    assert (bad.status_code, bad.json()["reason"]) == (422, "unknown_platform")
    assert SECRET not in bad.text

    vault.down = True
    down = await h.client.post("/v1/connected-accounts", json=_body())
    assert (down.status_code, down.json()["reason"]) == (503, "vault_unavailable")
    assert SECRET not in down.text
    assert (
        await h.client.post("/v1/connected-accounts", json={"platform": "mock-a"})
    ).status_code == 422
