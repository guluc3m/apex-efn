"""FastAPI application: OpenAI-compatible ``/v1`` surface plus the ``/_stub`` admin surface."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

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
    echo_price_text,
    prompt_tokens,
    render_content,
    usage_block,
)
from llm_stub.scenarios import (
    ScenarioError,
    load_scenarios,
    requested_schema,
    select_embedding_scenario,
    select_scenario,
)

SCENARIO_HEADER = "X-Stub-Scenario"
SCENARIOS_ENV = "LLM_STUB_SCENARIOS_DIR"
DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"
CALL_LOG_LIMIT = 1000


@dataclass
class CallRecord:
    """One received request, kept in the call log for assertions in tests."""

    index: int
    path: str
    scenario: str | None
    headers: dict[str, str]
    body: dict[str, Any]
    status: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class StubState:
    scenarios: dict[str, Scenario]
    call_log: list[CallRecord] = field(default_factory=list)
    # Per-scenario call counters: drive sequences and fail-N-times behaviour.
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def reset(self) -> None:
        self.counters = defaultdict(int)
        self.call_log = []


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
    elif scripted.kind == "echo_price":
        text = echo_price_text(
            req.messages, role="buyer" if req.model == "negotiator" else "seller"
        )
        message["content"] = text
        completion_text = text
        finish = scripted.finish_reason or "stop"
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


def _sse_lines(body: dict[str, Any]) -> list[str]:
    """Split a completion body into OpenAI-style SSE ``data:`` frames, ending with ``[DONE]``."""
    base = {
        "id": body["id"],
        "object": "chat.completion.chunk",
        "created": body["created"],
        "model": body["model"],
    }
    choice = body["choices"][0]
    msg = choice["message"]
    frames: list[dict[str, Any]] = [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    ]
    if msg.get("tool_calls"):
        tc = msg["tool_calls"][0]
        frames.append(
            {
                **base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tc["function"]["name"],
                                        "arguments": tc["function"]["arguments"],
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )
    else:
        content = msg.get("content") or ""
        # Emit in 16-char pieces so consumers really exercise incremental assembly.
        for i in range(0, len(content), 16):
            frames.append(
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content[i : i + 16]},
                            "finish_reason": None,
                        }
                    ],
                }
            )
    frames.append(
        {
            **base,
            "choices": [{"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}],
            "usage": body["usage"],
        }
    )
    lines = [f"data: {json.dumps(f)}\n\n" for f in frames]
    lines.append("data: [DONE]\n\n")
    return lines


def _resolve(state: StubState, header: str | None, req: ChatRequest) -> Scenario | None:
    try:
        return select_scenario(
            state.scenarios,
            header_name=header,
            model=req.model,
            messages=req.messages,
            schema=requested_schema(req.messages, req.response_format, req.tools),
        )
    except ScenarioError:
        return None


def _record(
    state: StubState, request: Request, scenario: str | None, body: Any, response: Response
) -> Response:
    """Append the received request to the call log and return ``response`` unchanged."""
    headers = {
        k.lower(): v
        for k, v in request.headers.items()
        if k.lower() not in {"authorization", "cookie"}
    }
    state.call_log.append(
        CallRecord(
            index=len(state.call_log),
            path=request.url.path,
            scenario=scenario,
            headers=headers,
            body=body if isinstance(body, dict) else {"_raw": str(body)},
            status=response.status_code,
        )
    )
    if len(state.call_log) > CALL_LOG_LIMIT:
        del state.call_log[0 : len(state.call_log) - CALL_LOG_LIMIT]
    return response


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
            return _record(state, request, None, raw, not_found)

        caps = scenario.caps_for(req.model)
        async with state.lock:
            index = state.counters[scenario.name]
            state.counters[scenario.name] += 1
        beh = scenario.behaviour

        # Fail-N-times-then-succeed comes first: a flaky endpoint fails regardless of the request.
        if index < beh.fail_times:
            return _record(state, request, scenario.name, raw, _error_response(beh.fail_with))

        cap_error = _check_capabilities(req, caps)
        if cap_error is not None:
            return _record(state, request, scenario.name, raw, cap_error)

        scripted = scenario.response_for_call(index)
        if beh.timeout_sleep_ms:
            await asyncio.sleep(beh.timeout_sleep_ms / 1000)
        if scripted.delay_ms:
            await asyncio.sleep(scripted.delay_ms / 1000)

        if scripted.kind == "error" and scripted.error is not None:
            return _record(state, request, scenario.name, raw, _error_response(scripted.error))

        body = _build_completion(scenario, req, scripted)
        if req.stream:
            lines = _sse_lines(body)

            async def gen() -> AsyncIterator[str]:
                for line in lines:
                    yield line

            stream = StreamingResponse(gen(), media_type="text/event-stream")
            return _record(state, request, scenario.name, raw, stream)
        return _record(state, request, scenario.name, raw, JSONResponse(content=body))

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
            return _record(
                state, request, None, raw, _unsupported(str(exc), code="scenario_not_found")
            )
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
        return _record(state, request, scenario.name, raw, JSONResponse(content=body))

    # ---- admin surface, deliberately outside /v1 ----

    @app.post("/_stub/reset")
    async def admin_reset() -> dict[str, str]:
        async with state.lock:
            state.reset()
        return {"status": "reset"}

    @app.get("/_stub/scenarios")
    async def admin_scenarios() -> dict[str, Any]:
        return {
            "scenarios": [
                {
                    "name": s.name,
                    "description": s.description,
                    "models": s.models,
                    "role": s.role,
                    "schema": s.schema_name,
                    "prompt_sha256": s.prompt_sha256,
                    "capabilities": {k: v.model_dump() for k, v in s.capabilities.items()},
                    "calls": state.counters.get(s.name, 0),
                }
                for s in state.scenarios.values()
            ]
        }

    @app.get("/_stub/calls")
    async def admin_calls() -> dict[str, Any]:
        return {
            "calls": [
                {
                    "index": c.index,
                    "path": c.path,
                    "scenario": c.scenario,
                    "status": c.status,
                    "headers": c.headers,
                    "body": c.body,
                }
                for c in state.call_log
            ]
        }

    @app.delete("/_stub/calls")
    async def admin_clear_calls() -> dict[str, str]:
        async with state.lock:
            state.call_log = []
        return {"status": "cleared"}

    return app
