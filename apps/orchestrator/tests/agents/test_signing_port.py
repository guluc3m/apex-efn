"""``SigningDecisionPort``: the graph's view of ``apex.signing.api`` (D2-09).

DEV-2's exception classes are injected, so these tests use stand-ins with the same names. When D2-09 merges,
the wiring passes the real classes and this file keeps working.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from apex.agents.ports import DecisionRejected, PendingSignature
from apex.agents.signing_port import SigningDecisionPort, SigningIntegrityError

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"


class FakePendingSignature(Exception):
    """Stands in for ``apex.signing.api.PendingSignature``."""


class FakeDecisionRejected(Exception):
    """Stands in for ``apex.signing.api.DecisionRejected``."""


class FakeSignatureInvalid(Exception):
    """Stands in for ``apex.signing.api.SignatureInvalid``."""


@dataclass
class _Ref:
    id: str
    status: Any


@dataclass
class _Signed:
    id: str
    type: Any
    subject_ref: str
    payload: Mapping[str, Any]
    signer_count: int


class _Status:
    def __init__(self, value: str) -> None:
        self.value = value


class _Type:
    def __init__(self, value: str) -> None:
        self.value = value


class _Backend:
    def __init__(self, *, signed: Any = None, raises: BaseException | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.signed = signed
        self.raises = raises

    async def create_decision(
        self, type: str, subject_ref: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> Any:
        self.calls.append(
            {"type": type, "subject_ref": subject_ref, "payload": payload, "tenant_id": tenant_id}
        )
        return _Ref(id="dec-1", status=_Status("pending_signature"))

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Any:
        self.calls.append({"decision_id": decision_id, "tenant_id": tenant_id})
        if self.raises is not None:
            raise self.raises
        return self.signed

    async def sign_service_event(
        self, service: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> Any:
        self.calls.append({"service": service, "payload": payload, "tenant_id": tenant_id})
        return "sig-1"


def _port(backend: _Backend) -> SigningDecisionPort:
    return SigningDecisionPort(
        backend,
        pending=(FakePendingSignature,),
        rejected=(FakeDecisionRejected,),
        invalid=(FakeSignatureInvalid,),
    )


# ----- creating a decision -----------------------------------------------------------------------


async def test_create_decision_passes_the_tenant_and_returns_the_graph_shape() -> None:
    backend = _Backend()
    ref = await _port(backend).create_decision(
        "gate_unblock", "offer:1", {"amount_minor": 445}, tenant_id=TENANT
    )
    assert ref.id == "dec-1"
    assert ref.status == "pending_signature"
    assert backend.calls == [
        {
            "type": "gate_unblock",
            "subject_ref": "offer:1",
            "payload": {"amount_minor": 445},
            "tenant_id": TENANT,
        }
    ]


# ----- reading a signed decision -----------------------------------------------------------------


async def test_a_signed_decision_is_mapped_with_its_payload_and_signer_count() -> None:
    backend = _Backend(
        signed=_Signed(
            id="dec-1",
            type=_Type("gate_unblock"),
            subject_ref="offer:1",
            payload={"amount_minor": 445, "config_version": 7},
            signer_count=2,
        )
    )
    view = await _port(backend).require_signed("dec-1", tenant_id=TENANT)
    assert view.id == "dec-1"
    assert view.type == "gate_unblock"
    assert view.payload["config_version"] == 7
    assert view.signer_count == 2


async def test_a_pending_decision_raises_the_graph_exception() -> None:
    with pytest.raises(PendingSignature):
        await _port(_Backend(raises=FakePendingSignature("dec-1"))).require_signed(
            "dec-1", tenant_id=TENANT
        )


async def test_a_rejected_decision_raises_the_graph_exception() -> None:
    with pytest.raises(DecisionRejected):
        await _port(_Backend(raises=FakeDecisionRejected("dec-1"))).require_signed(
            "dec-1", tenant_id=TENANT
        )


async def test_a_tampered_decision_is_never_reported_as_pending_or_rejected() -> None:
    """A signature that does not verify is tampering, not a state: it must not be retried as "not yet"."""
    with pytest.raises(SigningIntegrityError, match="does not verify"):
        await _port(_Backend(raises=FakeSignatureInvalid("hash mismatch"))).require_signed(
            "dec-1", tenant_id=TENANT
        )


async def test_without_injected_classes_every_failure_propagates_unchanged() -> None:
    """Before D2-09 is wired, nothing is silently reclassified."""
    port = SigningDecisionPort(_Backend(raises=FakePendingSignature("dec-1")))
    with pytest.raises(FakePendingSignature):
        await port.require_signed("dec-1", tenant_id=TENANT)


# ----- service events ----------------------------------------------------------------------------


async def test_a_service_event_returns_a_stable_id() -> None:
    backend = _Backend()
    signature = await _port(backend).sign_service_event(
        "orchestrator", {"event": "offer_discovered"}, tenant_id=TENANT
    )
    assert signature == "sig-1"
    assert backend.calls[0]["service"] == "orchestrator"
