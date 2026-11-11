"""``PdfDocumentService``: the ``DocumentService`` the post-decision flow calls (D2-11, D4-14).

Loads the decision and its signatures under the tenant's RLS, re-verifies them, renders the PDF and writes it to an
injected store. The store key holds the content hash, so a stored document is never silently replaced.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.agents.post_decision import DocumentKind, DocumentRef, DocumentRequest
from apex.db.models import DecisionStatus
from apex.db.session import tenant_session
from apex.documents.render import DocumentError, SignatureRecord, render
from apex.signing import decisions, jcs

_KIND = {
    DocumentKind.RFQ: "rfq",
    DocumentKind.PURCHASE_ORDER: "purchase_order",
    DocumentKind.VERIFICATION_CERTIFICATE: "verification_certificate",
}


class DocumentStore(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> None: ...


class PdfDocumentService:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], store: DocumentStore
    ) -> None:
        self._sessions, self._store = sessionmaker, store

    async def generate(self, request: DocumentRequest) -> DocumentRef:
        async with tenant_session(request.tenant_id, sessionmaker=self._sessions) as session:
            check = await decisions.verify(session, request.decision_id)
        row = check.decision
        kind = _KIND[request.kind]
        signed = check.intact and check.enough_signers and row.status == DecisionStatus.SIGNED
        if kind != "rfq" and not signed:
            raise DocumentError(f"decision {row.id} is not a verified signed decision")
        document = render(
            kind,
            decision_id=row.id,
            tenant_id=request.tenant_id,
            payload=jcs.loads(row.payload_canonical),
            signatures=[
                SignatureRecord(
                    s.id,
                    s.signer_id,
                    s.key_id,
                    s.payload_hash,
                    s.chain_hash,
                    s.prev_signature_hash,
                    s.signed_at,
                )
                for s in check.signatures
            ],
            generated_at=request.requested_at,
        )
        key = f"documents/{request.tenant_id}/{row.id}/{kind}-{document.sha256}.pdf"
        self._store.put(key, document.content, "application/pdf")
        return DocumentRef(document_id=document.sha256, kind=request.kind, url=key)
