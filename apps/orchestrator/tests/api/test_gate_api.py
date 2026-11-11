"""HTTP surface for D4-11: gate queue, gate actions, dashboard deals and deal actions."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.agents.gate import (
    DealAction,
    GateAgent,
    GateDeps,
    GateQueueItem,
    GateRules,
    InMemoryGateStore,
    deal_view,
)
from apex.agents.offers import Offer, OfferAnalysis
from apex.agents.ports import (
    ConfidenceBand,
    DecisionRef,
    FitOutcome,
    PriceBand,
    SanityOutcome,
    TrustOutcome,
)
from apex.api import dashboard as dashboard_api
from apex.api import gate as gate_api
from apex.common.clock import FixedClock
from apex.common.errors import install_problem_handlers

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
RULES = GateRules(sla_hours=24, max_renegotiations=1, stretch_gate_threshold_eur_minor=500_000)


class _Decisions:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create_decision(
        self, type: str, subject_ref: str, payload: Any, *, tenant_id: str
    ) -> DecisionRef:
        self.created.append({"type": type, "payload": dict(payload)})
        return DecisionRef(id=f"d{len(self.created)}", status="pending_signature")

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Any:
        raise NotImplementedError

    async def sign_service_event(self, service: str, payload: Any, *, tenant_id: str) -> str:
        return "sig"


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> str:
        self.n += 1
        return f"g{self.n}"


def _offer(**overrides: Any) -> Offer:
    base: dict[str, Any] = {
        "id": "o-1", "tenant_id": TENANT, "mission_id": "m-1", "platform_id": "mock-a",
        "seller_id": "s-1", "product_id": "p-1", "unit_price_eur_minor": 412,
        "list_price_eur_minor": 500, "currency": "EUR", "quantity": 100,
        "collected_at": NOW, "raw_signals": {},
    }  # fmt: skip
    return Offer(**{**base, **overrides})


def _analysis(**overrides: Any) -> OfferAnalysis:
    values: dict[str, Any] = {
        "price": PriceBand.NORMAL,
        "confidence": ConfidenceBand.HIGH,
        "verdict": "within_budget",
        "stale": False,
        "fx": False,
    }
    values.update(overrides)
    return OfferAnalysis(
        offer_id="o-1",
        confidence=TrustOutcome(band=values["confidence"], score=80, model_version="trust-v3"),
        sanity=SanityOutcome(band=values["price"], config_version="cfg-7"),
        fit=FitOutcome(
            verdict=values["verdict"],
            financials_stale=values["stale"],
            fx_provisional=values["fx"],
        ),  # type: ignore[arg-type]
        analysed_at=NOW,
    )


class _Dashboard:
    """Stands in for the wiring: one offer with one analysis and an optional gate item."""

    def __init__(self, agent: GateAgent, store: InMemoryGateStore) -> None:
        self.agent = agent
        self.store = store
        self.offer = _offer()
        self.analysis = _analysis(price=PriceBand.ATYPICAL)
        self.renegotiations_used = 0

    async def deals(
        self,
        *,
        tenant_id: str,
        platform: str | None,
        price_band: str | None,
        verdict: str | None,
        signature_status: str | None = None,
    ) -> list[Any]:
        item = await self.store.find_for_offer(tenant_id, self.offer.id)
        blocked = self.agent.blocked_deal_actions(
            offer=self.offer,
            analysis=self.analysis,
            rules=RULES,
            renegotiations_used=self.renegotiations_used,
            gate_item=item,
        )
        view = deal_view(offer=self.offer, analysis=self.analysis, gate_item=item, blocked=blocked)
        if platform and platform != self.offer.platform_id:
            return []
        if price_band and price_band != self.analysis.sanity.band.value:
            return []
        if verdict and verdict != self.analysis.fit.verdict:
            return []
        return [view]

    async def gate_item(self, *, tenant_id: str, item_id: str) -> Any:
        return await self.store.get(tenant_id, item_id)

    async def negotiation_for(self, *, tenant_id: str, offer_id: str) -> Any:
        return None

    async def decide(
        self,
        *,
        tenant_id: str,
        offer_id: str,
        action: DealAction,
        discard_reason: Any,
        comment: str | None,
        roles: list[str],
    ) -> DecisionRef:
        if offer_id != self.offer.id:
            raise LookupError(f"deal {offer_id} not found")
        item = await self.store.find_for_offer(tenant_id, self.offer.id)
        return await self.agent.decide_deal_action(
            tenant_id=tenant_id,
            offer=self.offer,
            analysis=self.analysis,
            action=action,
            rules=RULES,
            renegotiations_used=self.renegotiations_used,
            gate_item=item,
            discard_reason=discard_reason,
            comment=comment,
            roles=roles,
        )


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    store = InMemoryGateStore()
    decisions = _Decisions()
    agent = GateAgent(
        GateDeps(store=store, decisions=decisions, clock=FixedClock(NOW), ids=_Ids())  # type: ignore[arg-type]
    )
    dashboard = _Dashboard(agent, store)
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(gate_api.router, prefix="/gate")
    application.include_router(dashboard_api.router, prefix="/dashboard")
    application.dependency_overrides[gate_api.get_gate_agent] = lambda: agent
    application.dependency_overrides[dashboard_api.get_dashboard] = lambda: dashboard
    application.state.gate_agent = agent
    application.state.gate_store = store
    application.state.decisions = decisions
    yield application


def _h(tenant: str = TENANT) -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


def _enqueue(app: FastAPI) -> GateQueueItem:
    import asyncio

    agent: GateAgent = app.state.gate_agent
    item = asyncio.run(
        agent.enqueue(
            tenant_id=TENANT,
            offer=_offer(),
            analysis=_analysis(price=PriceBand.ATYPICAL),
            rules=RULES,
        )
    )
    assert item is not None
    return item


# ----- gate queue --------------------------------------------------------------------------------


def test_the_queue_lists_open_items_with_their_causes(app: FastAPI) -> None:
    item = _enqueue(app)
    with TestClient(app) as client:
        response = client.get("/gate/queue", headers=_h())
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == item.id
    assert items[0]["causes"] == ["price_atypical"]
    assert items[0]["status"] == "open"


def test_the_queue_is_empty_for_another_tenant(app: FastAPI) -> None:
    _enqueue(app)
    with TestClient(app) as client:
        assert client.get("/gate/queue", headers=_h("tenant-b")).json()["items"] == []


def test_unblock_creates_a_signed_decision(app: FastAPI) -> None:
    item = _enqueue(app)
    with TestClient(app) as client:
        response = client.post(
            f"/gate/queue/{item.id}/actions", json={"action": "unblock"}, headers=_h()
        )
    assert response.status_code == 202
    assert response.json()["decision_id"] == "d1"
    assert app.state.decisions.created[0]["type"] == "gate_unblock"


def test_override_discard_without_a_role_is_409_with_a_reason(app: FastAPI) -> None:
    item = _enqueue(app)
    with TestClient(app) as client:
        response = client.post(
            f"/gate/queue/{item.id}/actions",
            json={"action": "override_discard", "comment": "checked"},
            headers=_h(),
        )
    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == "role_not_allowed"
    assert body["blocked"][0]["reason"] == "role_not_allowed"


def test_override_discard_with_an_allowed_role_succeeds(app: FastAPI) -> None:
    """Roles come from the principal, so the test overrides the dependency rather than the body."""
    from apex.common.tenant import get_roles

    item = _enqueue(app)
    app.dependency_overrides[get_roles] = lambda: ("finance",)
    with TestClient(app) as client:
        response = client.post(
            f"/gate/queue/{item.id}/actions",
            json={"action": "override_discard", "comment": "checked"},
            headers=_h(),
        )
    assert response.status_code == 202
    assert app.state.decisions.created[0]["type"] == "gate_override_discard"


def test_acting_on_an_unknown_item_is_409_not_500(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/gate/queue/nope/actions", json={"action": "unblock"}, headers=_h())
    assert response.status_code == 409
    assert response.json()["reason"] == "not_in_queue"


# ----- dashboard ---------------------------------------------------------------------------------


def test_deals_are_the_contract_deal_page_and_explain_every_blocked_action(app: FastAPI) -> None:
    from apex.contracts.generated.models import DealPage

    _enqueue(app)
    with TestClient(app) as client:
        response = client.get("/dashboard/deals", headers=_h())
    assert response.status_code == 200
    page = DealPage.model_validate(response.json())  # the web reads exactly this shape
    deal = page.items[0]
    assert deal.id == "o-1" and deal.offer.id == "o-1"
    assert deal.price_band.value == "atypical"
    assert deal.state.value == "open" and deal.signature_status.value == "unsigned"
    assert deal.flags  # the gate causes
    actions = {a.action.value: a for a in deal.actions}
    assert not actions["follow"].allowed
    assert "price_band_requires_unblock" in {b.code.value for b in actions["follow"].blocked_by}
    assert all(b.message for b in actions["follow"].blocked_by)
    assert all(actions[a].allowed for a in ("takeover", "hold", "discard"))


def test_deals_filters(app: FastAPI) -> None:
    _enqueue(app)
    with TestClient(app) as client:

        def items(query: str = "") -> list[dict[str, object]]:
            out: list[dict[str, object]] = client.get(
                f"/dashboard/deals{query}", headers=_h()
            ).json()["items"]
            return out

        assert len(items()) == 1
        assert items("?platform=mock-b") == []
        assert items("?price_band=normal") == []
        assert len(items("?price_band=atypical")) == 1
        assert items("?mission_id=other") == []
        assert items("?signature_status=signed") == []
        assert len(items("?signature_status=unsigned")) == 1


def test_a_blocked_deal_action_is_409_with_every_reason(app: FastAPI) -> None:
    _enqueue(app)
    with TestClient(app) as client:
        response = client.post(
            "/dashboard/deals/o-1/actions", json={"action": "follow"}, headers=_h()
        )
    assert response.status_code == 409
    assert response.json()["reason"] == "price_band_requires_unblock"
    assert app.state.decisions.created == []


def test_a_discard_needs_a_reason_code(app: FastAPI) -> None:
    _enqueue(app)
    with TestClient(app) as client:
        missing = client.post(
            "/dashboard/deals/o-1/actions", json={"action": "discard"}, headers=_h()
        )
        ok = client.post(
            "/dashboard/deals/o-1/actions",
            json={"action": "discard", "discard_reason": "price_too_high", "comment": "overpriced"},
            headers=_h(),
        )
    assert missing.status_code == 409
    assert missing.json()["reason"] == "comment_required"
    assert ok.status_code == 202
    assert app.state.decisions.created[0]["payload"]["discard_reason"] == "price_too_high"


def test_an_unknown_deal_is_404(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/dashboard/deals/nope/actions", json={"action": "hold"}, headers=_h()
        )
    assert response.status_code == 404


def test_gate_and_dashboard_need_a_tenant(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)
    with TestClient(app) as client:
        assert client.get("/gate/queue", headers=_h()).status_code == 401
        assert client.get("/dashboard/deals", headers=_h()).status_code == 401


def test_roles_are_never_read_from_the_request_body(app: FastAPI) -> None:
    """A caller must not be able to claim `admin` by adding a field (issue #218 item 3)."""
    item = _enqueue(app)
    with TestClient(app) as client:
        response = client.post(
            f"/gate/queue/{item.id}/actions",
            json={"action": "override_discard", "comment": "checked", "roles": ["admin"]},
            headers=_h(),
        )
    # The body is rejected outright: the contract has no `roles` field and the model forbids extras.
    assert response.status_code == 422
    assert app.state.decisions.created == []


def test_without_a_principal_every_role_gated_action_is_refused(app: FastAPI) -> None:
    """D1-05 has not landed, so there are no roles and `override_discard` fails closed."""
    from apex.common.tenant import get_roles

    app.dependency_overrides.pop(get_roles, None)
    item = _enqueue(app)
    with TestClient(app) as client:
        response = client.post(
            f"/gate/queue/{item.id}/actions",
            json={"action": "override_discard", "comment": "checked"},
            headers=_h(),
        )
    assert response.status_code == 409
    assert response.json()["reason"] == "role_not_allowed"


def test_the_gate_queue_is_the_contract_page(app: FastAPI) -> None:
    from apex.contracts.generated.models import GateQueuePage

    _enqueue(app)
    with TestClient(app) as client:
        body = client.get("/gate/queue", headers=_h()).json()
    page = GateQueuePage.model_validate(body)
    assert page.items[0].offer_id == "o-1" and page.next_cursor is None
