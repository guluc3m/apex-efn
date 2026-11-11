"""Onboarding (D4-07): import never activates, activation is signed and all-or-nothing, criterion 1."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apex.agents.onboarding import (
    CompanyProfile,
    InMemoryOnboardingStore,
    OnboardingDeps,
    OnboardingIncomplete,
    OnboardingService,
    OnboardingStatus,
    SnapshotNotActivatable,
    SnapshotStatus,
)
from apex.agents.ports import DecisionRef, PendingSignature, SignedDecisionView
from apex.common.clock import FixedClock

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
REPORT = {"rows_ok": 34, "rows_rejected": 2, "projection_enabled": False}


class _Importer:
    def __init__(self, report: dict[str, Any] | None = None) -> None:
        self.report = report or REPORT
        self.calls: list[dict[str, Any]] = []

    async def parse(
        self, content: bytes, *, base_currency: str, tenant_id: str, now: datetime
    ) -> Any:
        self.calls.append({"size": len(content), "base_currency": base_currency, "now": now})

        class _Result:
            report = self.report

        return _Result()


class _Objects:
    def __init__(self) -> None:
        self.stored: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes, *, content_type: str) -> str:
        self.stored[key] = content
        return key


class _Decisions:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.signed: dict[str, SignedDecisionView] = {}

    async def create_decision(
        self, type: str, subject_ref: str, payload: Any, *, tenant_id: str
    ) -> DecisionRef:
        self.created.append({"type": type, "subject_ref": subject_ref, "payload": dict(payload)})
        return DecisionRef(id=f"d{len(self.created)}", status="pending_signature")

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> SignedDecisionView:
        if decision_id not in self.signed:
            raise PendingSignature(decision_id)
        return self.signed[decision_id]

    async def sign_service_event(self, service: str, payload: Any, *, tenant_id: str) -> str:
        return "sig"

    def sign(self, decision_id: str, **overrides: Any) -> None:
        created = self.created[int(decision_id[1:]) - 1]
        self.signed[decision_id] = SignedDecisionView(
            id=decision_id,
            type=created["type"],
            subject_ref=created["subject_ref"],
            payload={**created["payload"], **overrides},
            signer_count=1,
        )


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> str:
        self.n += 1
        return f"i{self.n}"


def _service(
    *, stale_after_days: int = 45, clock: Any = None, store: Any = None
) -> tuple[OnboardingService, _Decisions, _Importer, _Objects]:
    decisions = _Decisions()
    importer = _Importer()
    objects = _Objects()
    service = OnboardingService(
        OnboardingDeps(
            store=store or InMemoryOnboardingStore(),
            importer=importer,
            objects=objects,
            decisions=decisions,
            clock=clock or FixedClock(NOW),
            ids=_Ids(),
            stale_after_days=stale_after_days,
            config_version=lambda tenant_id: "cfg-7",
        )
    )
    return service, decisions, importer, objects


async def _upload(service: OnboardingService, session_id: str = "i1") -> Any:
    return await service.upload_financial_csv(
        tenant_id=TENANT,
        session_id=session_id,
        content=b"period,metric,value_minor\n2026-09,cash_balance,100\n",
        filename="fin.csv",
        base_currency="EUR",
    )


# ----- sessions ----------------------------------------------------------------------------------


async def test_a_session_starts_empty_and_profiled_after_the_form() -> None:
    service, _, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    assert session.status is OnboardingStatus.STARTED
    assert session.profile.legal_name is None
    updated = await service.update_profile(
        tenant_id=TENANT,
        session_id=session.id,
        profile=CompanyProfile(legal_name="ACME", base_currency="EUR"),
    )
    assert updated.status is OnboardingStatus.PROFILED
    assert updated.profile.legal_name == "ACME"


async def test_sessions_are_tenant_scoped() -> None:
    service, _, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    with pytest.raises(LookupError):
        await service.update_profile(
            tenant_id="tenant-b", session_id=session.id, profile=CompanyProfile()
        )


# ----- the CSV never activates anything -----------------------------------------------------------


async def test_upload_stores_the_original_and_returns_the_report_without_activating() -> None:
    service, decisions, importer, objects = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    assert snapshot.status is SnapshotStatus.DRAFT
    assert snapshot.report == REPORT
    assert snapshot.config_version == "cfg-7"
    assert decisions.created == [], "an upload must never create a decision"
    assert len(objects.stored) == 1
    assert importer.calls[0]["base_currency"] == "EUR"
    assert importer.calls[0]["now"] == NOW


async def test_upload_moves_the_session_to_awaiting_activation() -> None:
    service, _, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    store = service._deps.store  # type: ignore[attr-defined]
    updated = await store.get_session(TENANT, session.id)
    assert updated.status is OnboardingStatus.AWAITING_SNAPSHOT_ACTIVATION
    assert updated.pending_snapshot_id == snapshot.id


# ----- activation is signed and all-or-nothing ----------------------------------------------------


async def test_activation_creates_a_decision_binding_the_report_digest() -> None:
    service, decisions, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
    )
    assert decision.status == "pending_signature"
    created = decisions.created[0]
    assert created["type"] == "financial_snapshot_activation"
    assert created["subject_ref"] == f"financial_snapshot:{snapshot.id}"
    assert created["payload"]["report_digest"].startswith("sha256:")


async def test_activation_is_refused_until_the_decision_is_signed() -> None:
    service, _, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
    )
    with pytest.raises(PendingSignature):
        await service.activate(
            tenant_id=TENANT,
            session_id=session.id,
            snapshot_id=snapshot.id,
            decision_id=decision.id,
        )
    store = service._deps.store  # type: ignore[attr-defined]
    assert (await store.get_snapshot(TENANT, snapshot.id)).status is SnapshotStatus.DRAFT


async def test_a_signed_activation_activates_and_completes_onboarding() -> None:
    service, decisions, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
    )
    decisions.sign(decision.id)
    activated = await service.activate(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id, decision_id=decision.id
    )
    assert activated.status is SnapshotStatus.ACTIVE
    assert activated.activated_at == NOW
    assert activated.activation_decision_id == decision.id
    store = service._deps.store  # type: ignore[attr-defined]
    completed = await store.get_session(TENANT, session.id)
    assert completed.status is OnboardingStatus.COMPLETE
    assert completed.active_snapshot_id == snapshot.id


async def test_a_tampered_report_is_refused_after_signing() -> None:
    service, decisions, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
    )
    decisions.sign(decision.id, report_digest="sha256:" + "0" * 64)
    with pytest.raises(SnapshotNotActivatable, match="report changed"):
        await service.activate(
            tenant_id=TENANT,
            session_id=session.id,
            snapshot_id=snapshot.id,
            decision_id=decision.id,
        )


async def test_a_decision_for_another_snapshot_cannot_activate() -> None:
    service, decisions, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    first = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=first.id
    )
    decisions.sign(decision.id)
    decisions.signed[decision.id] = decisions.signed[decision.id].model_copy(
        update={"subject_ref": "financial_snapshot:other"}
    )
    with pytest.raises(SnapshotNotActivatable, match="another snapshot"):
        await service.activate(
            tenant_id=TENANT, session_id=session.id, snapshot_id=first.id, decision_id=decision.id
        )


async def test_activating_a_second_snapshot_supersedes_the_first() -> None:
    service, decisions, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    first = await _upload(service, session.id)
    d1 = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=first.id
    )
    decisions.sign(d1.id)
    await service.activate(
        tenant_id=TENANT, session_id=session.id, snapshot_id=first.id, decision_id=d1.id
    )
    second = await _upload(service, session.id)
    d2 = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=second.id
    )
    decisions.sign(d2.id)
    await service.activate(
        tenant_id=TENANT, session_id=session.id, snapshot_id=second.id, decision_id=d2.id
    )
    store = service._deps.store  # type: ignore[attr-defined]
    old = await store.get_snapshot(TENANT, first.id)
    assert old.status is SnapshotStatus.SUPERSEDED
    assert old.superseded_at == NOW
    assert (await store.active_snapshot(TENANT)).id == second.id


async def test_an_already_active_snapshot_cannot_be_activated_again() -> None:
    service, decisions, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
    )
    decisions.sign(decision.id)
    await service.activate(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id, decision_id=decision.id
    )
    with pytest.raises(SnapshotNotActivatable, match="already active"):
        await service.request_activation(
            tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
        )


# ----- criterion 1 and staleness ------------------------------------------------------------------


async def test_a_mission_cannot_launch_without_an_active_snapshot() -> None:
    service, _, _, _ = _service()
    with pytest.raises(OnboardingIncomplete):
        await service.require_active_snapshot(tenant_id=TENANT)


async def test_an_active_snapshot_satisfies_the_launch_gate() -> None:
    service, decisions, _, _ = _service()
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
    )
    decisions.sign(decision.id)
    await service.activate(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id, decision_id=decision.id
    )
    assert (await service.require_active_snapshot(tenant_id=TENANT)).id == snapshot.id


async def test_financials_become_stale_after_the_configured_window() -> None:
    clock = FixedClock(NOW)
    service, decisions, _, _ = _service(stale_after_days=45, clock=clock)
    session = await service.start_session(tenant_id=TENANT)
    snapshot = await _upload(service, session.id)
    decision = await service.request_activation(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id
    )
    decisions.sign(decision.id)
    await service.activate(
        tenant_id=TENANT, session_id=session.id, snapshot_id=snapshot.id, decision_id=decision.id
    )
    assert await service.is_financials_stale(tenant_id=TENANT) is False
    clock.advance(timedelta(days=45))
    assert await service.is_financials_stale(tenant_id=TENANT) is False  # exactly at the window
    clock.advance(timedelta(days=1))
    assert await service.is_financials_stale(tenant_id=TENANT) is True


async def test_no_active_snapshot_counts_as_stale() -> None:
    service, _, _, _ = _service()
    assert await service.is_financials_stale(tenant_id=TENANT) is True


# ----- IntakeAgent chat (D4-07b) -----------------------------------------------------------------


class _Gateway:
    def __init__(self, draft: Any) -> None:
        self.draft = draft
        self.calls: list[dict[str, Any]] = []

    async def chat_structured(self, role: Any, messages: Any, schema: Any, **kw: Any) -> Any:
        self.calls.append({"role": role, "messages": messages, **kw})
        return self.draft


def _chat_service(draft: Any) -> tuple[OnboardingService, _Gateway]:
    from apex.agents.intake_chat import IntakeChatAgent
    from apex.llm.prompts import PromptRegistry

    gateway = _Gateway(draft)
    service = OnboardingService(
        OnboardingDeps(
            store=InMemoryOnboardingStore(),
            importer=_Importer(),
            objects=_Objects(),
            decisions=_Decisions(),
            clock=FixedClock(NOW),
            ids=_Ids(),
            stale_after_days=45,
            config_version=lambda tenant_id: "cfg-7",
            intake=IntakeChatAgent(gateway, PromptRegistry()),  # type: ignore[arg-type]
        )
    )
    return service, gateway


def _draft(**profile: Any) -> Any:
    from apex.agents.schemas import IntakeProfileDraft, IntakeTurnDraft

    return IntakeTurnDraft(reply="Gracias.", profile=IntakeProfileDraft(**profile))


async def test_a_chat_turn_stores_both_messages_and_applies_only_valid_fields() -> None:
    service, gateway = _chat_service(
        _draft(legal_name=" ACME ", country="es", base_currency="GBP", sector="Packaging")
    )
    session = await service.start_session(tenant_id=TENANT)
    await service.update_profile(
        tenant_id=TENANT,
        session_id=session.id,
        profile=CompanyProfile(budget_eur_minor=1_234_500),
    )
    messages, updated = await service.send_message(
        tenant_id=TENANT, session_id=session.id, text="Somos ACME de España"
    )
    assert [m.role for m in messages] == ["user", "agent"]
    assert updated.profile.legal_name == "ACME"
    assert updated.profile.country == "ES"
    assert updated.profile.sector == "Packaging"
    assert updated.profile.base_currency is None  # GBP is not a supported currency: dropped
    assert updated.profile.budget_eur_minor == 1_234_500  # never touched by the agent
    assert "1234500" not in str(
        gateway.calls[0]["messages"]
    )  # financial values stay out of the prompt
    stored = await service.list_messages(tenant_id=TENANT, session_id=session.id)
    assert [m.text for m in stored] == ["Somos ACME de España", "Gracias."]


async def test_a_failed_model_call_stores_nothing() -> None:
    service, gateway = _chat_service(None)

    async def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("down")

    gateway.chat_structured = boom  # type: ignore[method-assign]
    session = await service.start_session(tenant_id=TENANT)
    with pytest.raises(RuntimeError):
        await service.send_message(tenant_id=TENANT, session_id=session.id, text="hola")
    assert await service.list_messages(tenant_id=TENANT, session_id=session.id) == []


async def test_chat_is_tenant_scoped() -> None:
    service, _ = _chat_service(_draft())
    session = await service.start_session(tenant_id=TENANT)
    with pytest.raises(LookupError):
        await service.send_message(tenant_id="tenant-b", session_id=session.id, text="hola")
