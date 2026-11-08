"""Scenario fixture models and the OpenAI-wire request/response shapes used by the stub."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ResponseKind = Literal["json", "text", "tool_call", "error"]
ErrorStatus = Literal[400, 401, 403, 404, 408, 409, 422, 429, 500, 502, 503, 504]


class Capabilities(BaseModel):
    """Per-model capability declaration. Anything not declared is treated as unsupported."""

    model_config = ConfigDict(extra="forbid")

    supports_json_schema: bool = False
    supports_json_object: bool = False
    supports_tools: bool = False
    supports_streaming: bool = False
    supports_seed: bool = False
    supports_guided: bool = False


class ErrorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ErrorStatus = 500
    message: str = "stub injected error"
    type: str = "server_error"
    retry_after: int | None = None


class ToolCallSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] | str = Field(default_factory=dict)
    id: str = "call_stub_0"


class Response(BaseModel):
    """One scripted response. Exactly one payload field is used, selected by ``kind``."""

    model_config = ConfigDict(extra="forbid")

    kind: ResponseKind = "text"
    content: str | dict[str, Any] | list[Any] | None = None
    tool_call: ToolCallSpec | None = None
    error: ErrorSpec | None = None
    # Latency applied before answering (ms). Applied to any kind.
    delay_ms: int = Field(default=0, ge=0)
    # Override usage counters for this response (forces large token counts, etc.).
    usage: dict[str, int] | None = None
    # Optional prompt/completion token override
    finish_reason: str | None = None

    @model_validator(mode="after")
    def _check_payload(self) -> Response:
        if self.kind == "error" and self.error is None:
            raise ValueError("kind=error requires an 'error' block")
        if self.kind == "tool_call" and self.tool_call is None:
            raise ValueError("kind=tool_call requires a 'tool_call' block")
        if self.kind in ("json", "text") and self.content is None:
            raise ValueError(f"kind={self.kind} requires 'content'")
        return self


class Behaviour(BaseModel):
    """Scenario-level behaviour knobs."""

    model_config = ConfigDict(extra="forbid")

    # Fail-N-times-then-succeed: the first ``fail_times`` calls return ``fail_with``.
    fail_times: int = Field(default=0, ge=0)
    fail_with: ErrorSpec = Field(default_factory=lambda: ErrorSpec(status=503))
    # Sleep longer than the requester's timeout; the stub sleeps ``sleep_ms`` before answering.
    timeout_sleep_ms: int | None = Field(default=None, ge=0)
    # Use ``usage`` override for every response in this scenario.
    usage: dict[str, int] | None = None
    # Echo the request ``seed`` back into the response (``system_fingerprint``-style).
    echo_seed: bool = True


class Scenario(BaseModel):
    """A named scenario: matching rules, capabilities per model, and responses."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    # Matching
    models: list[str] = Field(default_factory=list)
    role: Literal["planner", "negotiator", "extractor", "narrator"] | None = None
    prompt_sha256: str | None = None
    # Capabilities keyed by model id. ``"*"`` applies to any model not listed.
    capabilities: dict[str, Capabilities] = Field(default_factory=dict)
    # Responses: either a single ``response`` repeated, or a ``sequence`` consumed in order.
    # The last sequence element repeats once exhausted.
    response: Response | None = None
    sequence: list[Response] = Field(default_factory=list)
    behaviour: Behaviour = Field(default_factory=Behaviour)
    # Embedding dimension used by /v1/embeddings for this scenario (defaults to 64).
    embedding_dim: int = Field(default=64, ge=1, le=4096)

    @model_validator(mode="after")
    def _check_responses(self) -> Scenario:
        if self.response is None and not self.sequence:
            raise ValueError(f"scenario '{self.name}' needs 'response' or 'sequence'")
        return self

    def caps_for(self, model: str) -> Capabilities:
        if model in self.capabilities:
            return self.capabilities[model]
        if "*" in self.capabilities:
            return self.capabilities["*"]
        return Capabilities()

    def response_for_call(self, call_index: int) -> Response:
        """Return the response for the ``call_index``-th (0-based) call of this scenario."""
        if self.sequence:
            return self.sequence[min(call_index, len(self.sequence) - 1)]
        assert self.response is not None  # guaranteed by validator
        return self.response


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list[Any] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None
    seed: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    # vLLM guided decoding / llama.cpp grammar pass-through fields.
    guided_json: dict[str, Any] | None = None
    grammar: str | None = None


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    input: str | list[str]
