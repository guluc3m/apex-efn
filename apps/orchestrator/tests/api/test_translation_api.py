"""Translate a transcript message (issue 161): read-only, closed refusals, prompt carries only the text."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.agents.schemas import MessageTranslation
from apex.agents.translation import MessageTranslator
from apex.api import negotiations as negotiations_api
from apex.api import translation as translation_api
from apex.common.errors import install_problem_handlers
from apex.llm.gateway import LLMGatewayError
from apex.llm.prompts import PromptRegistry
from apex.llm.redaction import RedactionViolation
from apex.negotiation.api import NegotiationControlService
from apex.negotiation.models import TranscriptMessage
from tests.negotiation.fakes import NOW, T, cooperative_seller, harness, params
from tests.negotiation.fakes import request as open_request


class _Gateway:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[Any] = []

    async def chat_structured(self, role: Any, messages: Any, schema: Any, **kw: Any) -> Any:
        self.calls.append((role, messages, kw))
        if self.error:
            raise self.error
        return MessageTranslation(text="traducido")


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


def _rig(gateway: _Gateway) -> tuple[TestClient, str]:
    h = harness(cooperative_seller())
    session = asyncio.run(h.engine.start(open_request(params()), idempotency_key="n1"))
    stored = asyncio.run(h.store.get(session.id))
    assert stored is not None
    stored.transcript.append(TranscriptMessage(seq=0, role="seller", text="价格 4.20 EUR", at=NOW))
    asyncio.run(h.store.save(stored))
    control = NegotiationControlService(h.engine)
    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(translation_api.router, prefix="/v1/negotiations")
    app.dependency_overrides[negotiations_api.get_negotiation_control] = lambda: control
    app.dependency_overrides[translation_api.get_translator] = lambda: MessageTranslator(
        gateway,  # type: ignore[arg-type]
        PromptRegistry(),
    )
    return TestClient(app), session.id


def _post(client: TestClient, nid: str, mid: str, lang: str = "es") -> Any:
    return client.post(
        f"/v1/negotiations/{nid}/messages/{mid}/translate",
        json={"target_language": lang},
        headers={"X-Tenant-Id": T},
    )


def test_translates_and_sends_only_the_message_text() -> None:
    gw = _Gateway()
    client, nid = _rig(gw)
    r = _post(client, nid, f"{nid}:0", "he")
    assert r.status_code == 200, r.text
    assert r.json() == {"message_id": f"{nid}:0", "target_language": "he", "text": "traducido"}
    role, messages, kw = gw.calls[0]
    assert role.value == "narrator" and kw["tenant_id"] == T
    assert "Hebrew" in messages[0]["content"]


def test_unknown_message_and_negotiation_are_404() -> None:
    client, nid = _rig(_Gateway())
    assert _post(client, nid, f"{nid}:999").json()["reason"] == "not_found"
    assert _post(client, "nope", "nope:0").status_code == 404


def test_sensitive_content_is_422_and_model_down_is_502() -> None:
    client, nid = _rig(_Gateway(RedactionViolation(["iban"])))
    r = _post(client, nid, f"{nid}:0")
    assert (r.status_code, r.json()["reason"]) == (422, "sensitive_content")
    client, nid = _rig(_Gateway(LLMGatewayError("down")))
    r = _post(client, nid, f"{nid}:0")
    assert (r.status_code, r.json()["reason"]) == (502, "translation_unavailable")


def test_invalid_language_is_422() -> None:
    client, nid = _rig(_Gateway())
    assert _post(client, nid, f"{nid}:0", "fr").status_code == 422
