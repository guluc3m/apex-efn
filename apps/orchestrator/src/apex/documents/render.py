"""RFQ, purchase order and signature verification certificate (D2-11, spec 5.10).

Pure: a document is a function of the decision, its signatures and ``generated_at`` (injected). Every document
carries a manifest (the canonical signed payload, its SHA-256 and each signature's hashes) both as visible text
and as a trailing PDF comment, so ``verify_document`` can re-check it from the bytes alone. The certificate shows
the seller's confidence as it was in the signed payload, i.e. at decision time, never recomputed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from apex.documents.pdf import text_pdf
from apex.signing import jcs

KINDS = ("rfq", "purchase_order", "verification_certificate")
_TITLES = {
    "rfq": "REQUEST FOR QUOTATION",
    "purchase_order": "PURCHASE ORDER",
    "verification_certificate": "SIGNATURE VERIFICATION CERTIFICATE",
}
_BEGIN, _END = b"APEX-MANIFEST:", b""


class DocumentError(Exception):
    pass


@dataclass(frozen=True)
class SignatureRecord:
    id: str
    signer_id: str
    key_id: str
    payload_hash: str
    chain_hash: str
    prev_signature_hash: str | None
    signed_at: datetime


@dataclass(frozen=True)
class Document:
    kind: str
    content: bytes
    sha256: str


def money(value: object) -> str:
    """``{amount_minor, currency}`` as text. EUR, USD and CNY all have two minor digits."""
    if not isinstance(value, Mapping):
        return "n/a"
    minor = int(value["amount_minor"])
    sign, minor = ("-" if minor < 0 else ""), abs(minor)
    return f"{sign}{minor // 100}.{minor % 100:02d} {value['currency']}"


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _manifest(
    kind: str,
    decision_id: str,
    tenant_id: str,
    payload: Mapping[str, Any],
    signatures: Sequence[SignatureRecord],
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "decision_id": decision_id,
        "tenant_id": tenant_id,
        "payload": payload,
        "payload_hash": jcs.payload_hash(payload),
        "signatures": [
            {
                "id": s.id,
                "signer_id": s.signer_id,
                "key_id": s.key_id,
                "payload_hash": s.payload_hash,
                "chain_hash": s.chain_hash,
                "prev_signature_hash": s.prev_signature_hash,
                "signed_at": _iso(s.signed_at),
            }
            for s in signatures
        ],
        "generated_at": _iso(generated_at),
    }


def _offer_lines(payload: Mapping[str, Any]) -> list[str]:
    confidence = payload.get("seller_confidence")
    sanity = payload.get("price_sanity")
    lines = [
        f"Offer: {payload.get('offer_id', 'n/a')}",
        f"Seller: {payload.get('seller_id', 'n/a')}",
        f"Amount: {money(payload.get('amount'))}",
    ]
    if isinstance(confidence, Mapping):
        lines.append(
            f"Seller confidence at decision time: {confidence.get('score')} ({confidence.get('band')}), "
            f"model {confidence.get('model_version')}"
        )
    if isinstance(sanity, Mapping):
        lines.append(f"Price band: {sanity.get('band', 'n/a')}")
    if payload.get("financial_verdict") is not None:
        lines.append(f"Financial verdict: {payload['financial_verdict']}")
    if payload.get("config_version") is not None:
        lines.append(f"Config version: {payload['config_version']}")
    return lines


def render(
    kind: str,
    *,
    decision_id: str,
    tenant_id: str,
    payload: Mapping[str, Any],
    signatures: Sequence[SignatureRecord],
    generated_at: datetime,
) -> Document:
    if kind not in KINDS:
        raise DocumentError(f"unknown document kind {kind!r}")
    if kind != "rfq" and not signatures:
        raise DocumentError(f"a {kind} needs a signed decision")
    manifest = _manifest(
        kind, decision_id, tenant_id, payload, signatures if kind != "rfq" else (), generated_at
    )
    lines = [
        f"Decision: {decision_id}",
        f"Tenant: {tenant_id}",
        f"Generated at: {manifest['generated_at']}",
        "",
    ]
    lines += _offer_lines(payload)
    lines += ["", f"Payload SHA-256: {manifest['payload_hash']}"]
    if kind != "rfq":
        lines += ["", "Signatures:"]
        for s in manifest["signatures"]:
            lines += [
                f"- {s['id']} by {s['signer_id']} with key {s['key_id']} at {s['signed_at']}",
                f"  chain hash: {s['chain_hash']}",
                f"  previous:   {s['prev_signature_hash']}",
            ]
    if kind == "verification_certificate":
        lines += [
            "",
            "To verify: canonicalize the payload (RFC 8785), hash it with SHA-256 and compare it with the",
            "payload hash above, then verify each Ed25519 signature over the canonical bytes.",
        ]
    comment = _BEGIN + jcs.canonical_bytes(manifest).replace(b"\n", b" ") + _END
    content = text_pdf(_TITLES[kind], lines, trailer_comment=comment)
    return Document(kind, content, hashlib.sha256(content).hexdigest())


def verify_document(content: bytes) -> dict[str, Any]:
    """Re-check a generated PDF from its bytes. Returns the manifest, or raises ``DocumentError``."""
    start = content.rfind(b"%" + _BEGIN)
    if start < 0:
        raise DocumentError("no APEX manifest in this document")
    raw = content[start + 1 + len(_BEGIN) :].split(b"\n", 1)[0]
    try:
        manifest: dict[str, Any] = jcs.loads(raw)
    except ValueError as error:
        raise DocumentError("the manifest is not valid JSON") from error
    expected = jcs.payload_hash(manifest["payload"])
    if manifest["payload_hash"] != expected:
        raise DocumentError("payload_hash is not the hash of the embedded payload")
    for sig in manifest["signatures"]:
        if sig["payload_hash"] != expected:
            raise DocumentError(f"signature {sig['id']} signs a different payload")
    visible = content[:start]
    for needle in [expected, *(s["chain_hash"] for s in manifest["signatures"])]:
        if needle.encode() not in visible:
            raise DocumentError("the visible text does not show the manifest hashes")
    return manifest
