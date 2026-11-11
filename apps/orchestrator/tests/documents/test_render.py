"""D2-11: the documents embed hashes that can be re-checked from the bytes alone."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apex.documents.pdf import text_pdf
from apex.documents.render import (
    KINDS,
    DocumentError,
    SignatureRecord,
    money,
    render,
    verify_document,
)
from apex.signing import jcs

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
PAYLOAD = {
    "action": "approve",
    "offer_id": "off_1",
    "seller_id": "sel_1",
    "amount": {"amount_minor": 1_234_567, "currency": "EUR"},
    "price_sanity": {"band": "normal"},
    "seller_confidence": {"score": 82, "band": "high", "model_version": "trust-v1"},
    "financial_verdict": "within_budget",
    "config_version": 7,
}
HASH = jcs.payload_hash(PAYLOAD)
SIGS = [SignatureRecord("sig_1", "user_1", "key_1", HASH, "c" * 64, None, NOW)]


def make(kind: str, payload=PAYLOAD, sigs=SIGS):
    return render(
        kind,
        decision_id="dec_1",
        tenant_id="t1",
        payload=payload,
        signatures=sigs,
        generated_at=NOW,
    )


@pytest.mark.parametrize("kind", KINDS)
def test_every_document_verifies_and_is_deterministic(kind: str) -> None:
    doc = make(kind)
    assert doc.content.startswith(b"%PDF-")
    assert make(kind).content == doc.content
    manifest = verify_document(doc.content)
    assert manifest["payload_hash"] == HASH and manifest["decision_id"] == "dec_1"


def test_certificate_shows_confidence_as_signed_not_recomputed() -> None:
    text = make("verification_certificate").content.decode("latin-1")
    assert "82 \\(high\\), model trust-v1" in text
    assert "c" * 64 in text


def test_flipping_the_embedded_payload_is_detected() -> None:
    content = make("purchase_order").content
    tampered = content.replace(b'"score":82', b'"score":99')
    assert tampered != content
    with pytest.raises(DocumentError, match="payload_hash"):
        verify_document(tampered)


def test_a_signature_over_another_payload_is_detected() -> None:
    other = SignatureRecord("sig_2", "user_2", "key_2", "0" * 64, "d" * 64, None, NOW)
    with pytest.raises(DocumentError, match="different payload"):
        verify_document(make("purchase_order", sigs=[other]).content)


def test_changing_the_visible_hash_is_detected() -> None:
    content = make("verification_certificate").content
    with pytest.raises(DocumentError, match="visible text"):
        verify_document(content.replace(HASH.encode(), b"f" * 64, 1))


def test_signed_documents_need_signatures_and_unknown_kinds_fail() -> None:
    make("rfq", sigs=[])
    with pytest.raises(DocumentError):
        make("purchase_order", sigs=[])
    with pytest.raises(DocumentError):
        make("invoice")


def test_money_is_exact_and_handles_negatives() -> None:
    assert money({"amount_minor": 1_234_567, "currency": "EUR"}) == "12345.67 EUR"
    assert money({"amount_minor": -5, "currency": "CNY"}) == "-0.05 CNY"
    assert money(None) == "n/a"


def test_long_text_paginates_and_escapes() -> None:
    pdf = text_pdf("t (x)", [f"line {i} \\ (" for i in range(130)])
    assert pdf.count(b"/Type /Page ") == 3
    assert b"\\(x\\)" in pdf
