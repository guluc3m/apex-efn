"""FastAPI application: OpenAI-compatible ``/v1`` surface (non-streaming)."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response

from llm_stub.models import (
    Capabilities,
    ChatRequest,
    EmbeddingRequest,
    ErrorSpec,
    Scenario,
)
from llm_stub.models import (
    Response as ScriptedResponse,
)
from llm_stub.render import (
    approx_tokens,
    deterministic_embedding,
    prompt_tokens,
    render_content,
    usage_block,
)
from llm_stub.scenarios import (
    ScenarioError,
    load_scenarios,
    select_embedding_scenario,
    select_scenario,
)

SCENARIO_HEADER = "X-Stub-Scenario"
SCENARIOS_ENV = "LLM_STUB_SCENARIOS_DIR"
DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"


@dataclass
class StubState:
    scenarios: dict[str, Scenario]
    # Per-scenario call counters: drive sequences and fail-N-times behaviour.
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def reset(self) -> None:
        self.counters = defaultdict(int)


def _error_body(spec: ErrorSpec) -> dict[str, Any]:
    return {"error": {"message": spec.message, "type": spec.type, "param": None, "code": None}}


def _error_response(spec: ErrorSpec) -> JSONResponse:
    headers: dict[str, str] = {}
    if spec.retry_after is not None:
        headers["Retry-After"] = str(spec.retry_after)
    return JSONResponse(status_code=spec.status, content=_error_body(spec), headers=headers)


def _unsupported(message: str, code: str = "unsupported_parameter") -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "param": None,
                "code": code,
            }
        },
    )


def _check_capabilities(req: ChatRequest, caps: Capabilities) -> JSONResponse | None:
    """Reject request features the matched model does not declare (OpenAI-style 400)."""
    rf = req.response_format
    if rf is not None:
        kind = rf.get("type")
        if kind == "json_schema" and not caps.supports_json_schema:
            return _unsupported(f"model '{req.model}' does not support response_format json_schema")
        if kind == "json_object" and not caps.supports_json_object:
            return _unsupported(f"model '{req.model}' does not support response_format json_object")
    if req.tools and not caps.supports_tools:
        return _unsupported(f"model '{req.model}' does not support tools")
    if req.stream and not caps.supports_streaming:
        return _unsupported(f"model '{req.model}' does not support streaming")
    if req.seed is not None and not caps.supports_seed:
        return _unsupported(f"model '{req.model}' does not support seed")
    if req.guided_json is not None and not caps.supports_guided:
        return _unsupported(f"model '{req.model}' does not support guided_json")
    if req.grammar is not None and not caps.supports_guided:
        return _unsupported(f"model '{req.model}' does not support grammar")
    return None


def _build_completion(
    scenario: Scenario, req: ChatRequest, scripted: ScriptedResponse
) -> dict[str, Any]:
    """Assemble the ``chat.completion`` body for a scripted response."""
    prompt = prompt_tokens(req.messages)
    message: dict[str, Any] = {"role": "assistant", "content": None}
    if scripted.kind == "tool_call" and scripted.tool_call is not None:
        tc = scripted.tool_call
        args = tc.arguments if isinstance(tc.arguments, str) else json.dumps(tc.arguments)
        message["tool_calls"] = [
            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": args}}
        ]
        completion_text = args
        finish = scripted.finish_reason or "tool_calls"
    else:
        text = render_content(scripted.content)
        message["content"] = text
        completion_text = text
        finish = scripted.finish_reason or "stop"
    override = scripted.usage or scenario.behaviour.usage
    body: dict[str, Any] = {
        "id": f"chatcmpl-stub-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish, "logprobs": None}],
        "usage": usage_block(prompt, approx_tokens(completion_text), override),
    }
    if req.seed is not None and scenario.behaviour.echo_seed:
        body["system_fingerprint"] = f"stub-seed-{req.seed}"
    return body


def _resolve(state: StubState, header: str | None, req: ChatRequest) -> Scenario | None:
    try:
        return select_scenario(
            state.scenarios, header_name=header, model=req.model, messages=req.messages
        )
    except ScenarioError:
        return None


def create_app(scenarios_dir: str | Path | None = None) -> FastAPI:
    """Build the stub application.

    ``scenarios_dir`` defaults to ``$LLM_STUB_SCENARIOS_DIR`` and then to the bundled ``scenarios/``.
    """
    directory = Path(
        scenarios_dir
        if scenarios_dir is not None
        else os.environ.get(SCENARIOS_ENV, DEFAULT_SCENARIOS_DIR)
    )
    state = StubState(scenarios=load_scenarios(directory))
    app = FastAPI(title="APEX-EFN LLM stub", version="0.1.0")
    app.state.stub = state

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        ids: set[str] = set()
        for s in state.scenarios.values():
            ids.update(s.models)
            ids.update(k for k in s.capabilities if k != "*")
        data = [
            {"id": mid, "object": "model", "created": 0, "owned_by": "llm-stub"}
            for mid in sorted(ids)
        ]
        return {"object": "list", "data": data}

    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(
        request: Request,
        x_stub_scenario: str | None = Header(default=None, alias=SCENARIO_HEADER),
    ) -> Response:
        raw = await request.json()
        req = ChatRequest.model_validate(raw)
        scenario = _resolve(state, x_stub_scenario, req)
        if scenario is None:
            not_found = _unsupported(
                f"unknown scenario '{x_stub_scenario}'", code="scenario_not_found"
            )
            return not_found

        caps = scenario.caps_for(req.model)
        async with state.lock:
            index = state.counters[scenario.name]
            state.counters[scenario.name] += 1
        beh = scenario.behaviour

        # Fail-N-times-then-succeed comes first: a flaky endpoint fails regardless of the request.
        if index < beh.fail_times:
            return _error_response(beh.fail_with)

        cap_error = _check_capabilities(req, caps)
        if cap_error is not None:
            return cap_error

        scripted = scenario.response_for_call(index)
        if beh.timeout_sleep_ms:
            await asyncio.sleep(beh.timeout_sleep_ms / 1000)
        if scripted.delay_ms:
            await asyncio.sleep(scripted.delay_ms / 1000)

        if scripted.kind == "error" and scripted.error is not None:
            return _error_response(scripted.error)

        body = _build_completion(scenario, req, scripted)
        return JSONResponse(content=body)

    @app.post("/v1/embeddings")
    async def embeddings(
        request: Request,
        x_stub_scenario: str | None = Header(default=None, alias=SCENARIO_HEADER),
    ) -> Response:
        raw = await request.json()
        req = EmbeddingRequest.model_validate(raw)
        try:
            scenario = select_embedding_scenario(state.scenarios, x_stub_scenario, req.model)
        except ScenarioError as exc:
            return _unsupported(str(exc), code="scenario_not_found")
        inputs = [req.input] if isinstance(req.input, str) else req.input
        data = [
            {
                "object": "embedding",
                "index": i,
                "embedding": deterministic_embedding(text, scenario.embedding_dim),
            }
            for i, text in enumerate(inputs)
        ]
        tokens = sum(approx_tokens(t) for t in inputs)
        body = {
            "object": "list",
            "data": data,
            "model": req.model,
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
        }
        return JSONResponse(content=body)

    return app
