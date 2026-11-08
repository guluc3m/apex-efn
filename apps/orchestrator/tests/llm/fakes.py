"""Local OpenAI-compatible fake used until the D4-02 stub is importable.

Records every request (path, JSON body, headers) so tests can assert exactly which parameters were sent.
Responses are scripted per call via ``queue``; the last scripted item repeats when the queue is empty.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from apex.llm.config import (
    CapabilityProfile,
    GuidedDecoding,
    LLMRole,
    LLMRolesConfig,
    RoleEndpointConfig,
    StaticRoleConfigProvider,
    StaticSecretResolver,
)

Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class Recorded:
    path: str
    body: dict[str, Any]
    headers: dict[str, str]


@dataclass
class FakeEndpoint:
    """Scriptable endpoint. Each queued item is a chat body dict, an HTTP error tuple, or a callable."""

    name: str = "fake"
    responses: list[Any] = field(default_factory=list)
    calls: list[Recorded] = field(default_factory=list)

    def queue(self, *items: Any) -> None:
        self.responses.extend(items)

    def _next(self) -> Any:
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.calls.append(Recorded(path=request.url.path, body=body, headers=dict(request.headers)))
        item = self._next()
        if callable(item):
            return item(request)
        if isinstance(item, tuple):
            status, text, headers = item
            return httpx.Response(status, text=text, headers=headers)
        return httpx.Response(200, json=item)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def chat_body(
    content: str, *, prompt: int = 10, completion: int = 5, model: str = "m"
) -> dict[str, Any]:
    return {
        "id": "x",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


def tool_body(arguments: str) -> dict[str, Any]:
    return {
        "id": "x",
        "object": "chat.completion",
        "model": "m",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "t",
                            "type": "function",
                            "function": {"name": "X", "arguments": arguments},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }


def endpoint_cfg(
    endpoint_id: str = "primary",
    *,
    base_url: str = "http://fake.local",
    caps: CapabilityProfile | None = None,
    fallback: list[str] | None = None,
    model: str = "model-a",
    max_output_tokens: int = 64,
    api_key_ref: str | None = "key/primary",
    cost: tuple[int, int] | None = None,
    gpu: float | None = None,
    seed: int | None = None,
) -> RoleEndpointConfig:
    return RoleEndpointConfig(
        endpoint_id=endpoint_id,
        base_url=base_url,
        api_key_ref=api_key_ref,
        model=model,
        capabilities=caps or CapabilityProfile(),
        max_output_tokens=max_output_tokens,
        fallback=fallback or [],
        cost_per_1k_prompt_minor=cost[0] if cost else None,
        cost_per_1k_completion_minor=cost[1] if cost else None,
        gpu_seconds_per_1k_tokens=gpu,
        seed=seed,
    )


def roles_config(
    primary: RoleEndpointConfig,
    *,
    extra: dict[str, RoleEndpointConfig] | None = None,
    role: LLMRole = LLMRole.EXTRACTOR,
) -> LLMRolesConfig:
    endpoints = {primary.endpoint_id: primary, **(extra or {})}
    return LLMRolesConfig(roles={role: primary}, endpoints=endpoints)


def provider(config: LLMRolesConfig) -> StaticRoleConfigProvider:
    return StaticRoleConfigProvider(config)


def secrets() -> StaticSecretResolver:
    return StaticSecretResolver(
        {"key/primary": "sk-test-SECRET-VALUE-0123456789", "key/small": "sk-small-0123456789abcdef"}
    )


__all__ = [
    "FakeEndpoint",
    "GuidedDecoding",
    "LLMRole",
    "SecretStr",
    "chat_body",
    "endpoint_cfg",
    "provider",
    "roles_config",
    "secrets",
    "tool_body",
]
