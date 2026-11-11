"""Approvals inbox: a view over approval decisions, with dual-control progress."""

from __future__ import annotations

from datetime import timedelta

from tests.signing.test_decisions import Desk, desk, gate
from tests.signing.test_keys import T0, app_db, h, migrated_db, pytestmark, seeded

__all__ = ["app_db", "desk", "h", "migrated_db", "pytestmark", "seeded"]


async def test_inbox_follows_dual_control_and_ignores_other_decisions(desk: Desk) -> None:
    desk.h.clock.set(T0 + timedelta(minutes=1))
    created = (await desk.create("alice", "deal_action", gate(2_500_000))).json()
    await desk.create("alice", "deal_action", {**gate(100), "action": "discard"})

    listed = (await desk.h.client.get("/v1/approvals?status=sign")).json()
    assert [i["id"] for i in listed["items"]] == [created["id"]]
    item = listed["items"][0]
    assert item["required_signers"] == 2 and item["signatures"] == []
    assert item["amount"] == {"amount_minor": 2_500_000, "currency": "EUR"}
    assert all(not d["available"] for d in item["documents"])

    await desk.sign("alice", created, await desk.window("alice", T0 + timedelta(minutes=2)))
    one = (await desk.h.client.get(f"/v1/approvals/{created['id']}")).json()
    assert one["status"] == "sign" and len(one["signatures"]) == 1
    await desk.sign("bob", created, await desk.window("bob", T0 + timedelta(minutes=3)))
    progress = (await desk.h.client.get("/v1/approvals?status=progress")).json()["items"]
    assert [i["id"] for i in progress] == [created["id"]]
    assert (await desk.h.client.get("/v1/approvals?status=closed")).json()["items"] == []
    assert (await desk.h.client.get("/v1/approvals/nope")).status_code == 404


async def test_documents_download_only_when_signed_and_finance_notice_is_audited(
    desk: Desk,
) -> None:
    desk.h.clock.set(T0 + timedelta(minutes=1))
    created = (await desk.create("carol", "deal_action", gate(2_500_000))).json()
    url = f"/v1/approvals/{created['id']}"

    blocked = await desk.h.client.get(f"{url}/documents/po")
    assert (blocked.status_code, blocked.json()["reason"]) == (409, "not_signed")

    notice = await desk.h.client.post(f"{url}/notify-finance")
    assert notice.status_code == 202 and notice.json()["approval_id"] == created["id"]
    desk.h.as_user("root", roles=("admin",))
    events = (await desk.h.client.get("/v1/audit?event_type=approval.finance_notified")).json()
    assert [e["event_type"] for e in events["items"]] == ["approval.finance_notified"]

    await desk.sign("carol", created, await desk.window("carol", T0 + timedelta(minutes=2)))
    await desk.sign("erin", created, await desk.window("erin", T0 + timedelta(minutes=3)))
    desk.h.as_user("carol")
    pdf = await desk.h.client.get(f"{url}/documents/certificate")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    done = await desk.h.client.post(f"{url}/notify-finance")
    assert (done.status_code, done.json()["reason"]) == (409, "not_pending")
    assert (await desk.h.client.get("/v1/approvals/nope/documents/po")).status_code == 404
