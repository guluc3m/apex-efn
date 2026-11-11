"""D2-11: the generator reads a really signed decision and refuses an unsigned one."""

from __future__ import annotations

from datetime import timedelta

import pytest

from apex.agents.post_decision import DocumentKind, DocumentRequest
from apex.documents.render import DocumentError, verify_document
from apex.documents.service import PdfDocumentService
from tests.signing.test_decisions import Desk, desk, gate
from tests.signing.test_keys import T0, TENANT, app_db, h, migrated_db, pytestmark, seeded

__all__ = [
    "app_db",
    "desk",
    "h",
    "migrated_db",
    "pytestmark",
    "seeded",
]  # fixtures and marks for pytest


class Store:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = body


def request(kind: DocumentKind, decision_id: str, at: object) -> DocumentRequest:
    return DocumentRequest(
        kind=kind,
        tenant_id=TENANT,
        mission_id="mission-1",
        offer_id="offer-1",
        decision_id=decision_id,
        requested_at=at,  # type: ignore[arg-type]
    )


async def test_documents_embed_the_real_signature_hashes(desk: Desk) -> None:
    at = T0 + timedelta(minutes=1)
    window = await desk.window("alice", at)
    decision = (await desk.create("alice", "deal_action", gate(500_000))).json()
    assert (await desk.sign("alice", decision, window)).status_code == 201
    store = Store()
    service = PdfDocumentService(desk.h.factory, store)

    ref = await service.generate(request(DocumentKind.VERIFICATION_CERTIFICATE, decision["id"], at))
    manifest = verify_document(store.objects[ref.url])

    assert manifest["payload_hash"] == decision["payload_hash"]
    assert [s["signer_id"] for s in manifest["signatures"]] == ["user-alice"]
    assert manifest["payload"]["seller_confidence"]["model_version"] == "trust-v1"
    po = await service.generate(request(DocumentKind.PURCHASE_ORDER, decision["id"], at))
    assert verify_document(store.objects[po.url])["kind"] == "purchase_order"


async def test_unsigned_decision_gets_an_rfq_but_no_purchase_order(desk: Desk) -> None:
    at = T0 + timedelta(minutes=1)
    await desk.window("bob", at)
    decision = (await desk.create("bob", "deal_action", gate(500_000))).json()
    service = PdfDocumentService(desk.h.factory, Store())

    await service.generate(request(DocumentKind.RFQ, decision["id"], at))
    with pytest.raises(DocumentError):
        await service.generate(request(DocumentKind.PURCHASE_ORDER, decision["id"], at))
