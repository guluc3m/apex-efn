"""OpenAI-compatible LLM access for the simulation (D5-11, spec 5.6).

The negotiation adapters (``apex.negotiation.llm``) need a ``GatewayLike``: ``chat`` to draft a message
and ``chat_structured`` to read the seller's quote. In production that is DEV-4's ``LLMGateway``; in the
simulation it is a thin client over ``{llm_url}/v1/chat/completions`` (the llm-stub of ``apps/llm-stub``
or any self-hosted OpenAI-compatible engine). Only the standard OpenAI contract is used: no vendor SDKs
and no proprietary endpoints.

When no ``llm_url`` is given, :class:`NullGateway` fails every call. That is deliberate: the engine
already knows how to degrade deterministically (template drafter, regex-grounded quote extraction), so
the simulation runs with templates only and never invents wording or numbers.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from apex.llm.config import LLMRole
from apex.llm.gateway import ChatResult
from apex.negotiation.llm import GatewayLike

__all__ = [
    "LLMError",
    "LLMUnavailable",
    "NullGateway",
    "OpenAICompatGateway",
    "SimGateway",
    "build_gateway",
]

M = TypeVar("M", bound=BaseModel)


class LLMError(RuntimeError):
    """The endpoint is reachable but did not return what the adapter expects."""


class LLMUnavailable(LLMError):
    """No LLM configured, or the endpoint cannot be reached."""


class SimGateway(GatewayLike, Protocol):
    """``GatewayLike`` plus the lifecycle hook the pipeline needs to close its HTTP client."""

    async def aclose(self) -> None: ...


class NullGateway:
    """Fails every call so the engine falls back to templates and the deterministic parser."""

    async def chat(
        self,
        role: LLMRole,
        messages: list[dict[str, str]],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        temperature: float | None = None,
        seed: int | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        raise LLMUnavailable("no llm_url configured: the simulation drafts with templates")

    async def chat_structured(
        self,
        role: LLMRole,
        messages: list[dict[str, str]],
        schema: type[M],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> M:
        raise LLMUnavailable("no llm_url configured: quotes are parsed deterministically")

    async def aclose(self) -> None:
        return


class OpenAICompatGateway:
    """Minimal OpenAI-compatible chat client. Temperature is pinned to 0 by the callers."""

    def __init__(self, base_url: str, *, model: str = "negotiator", timeout: float = 30.0) -> None:
        root = base_url.rstrip("/")
        self._url = (
            f"{root}/chat/completions" if root.endswith("/v1") else f"{root}/v1/chat/completions"
        )
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        role: LLMRole,
        messages: list[dict[str, str]],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        temperature: float | None = None,
        seed: int | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.0 if temperature is None else temperature,
        }
        if seed is not None:
            payload["seed"] = seed
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        started = time.perf_counter()
        body = await self._post(payload)
        latency_ms = (time.perf_counter() - started) * 1_000
        content = _content(body)
        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return ChatResult(
            content=content,
            endpoint_id="sim-llm",
            model=str(body.get("model", self._model)),
            tokens_in=_token_count(usage.get("prompt_tokens")),
            tokens_out=_token_count(usage.get("completion_tokens")),
            latency_ms=latency_ms,
        )

    async def chat_structured(
        self,
        role: LLMRole,
        messages: list[dict[str, str]],
        schema: type[M],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> M:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.0 if temperature is None else temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            },
        }
        if seed is not None:
            payload["seed"] = seed
        body = await self._post(payload)
        raw = _content(body)
        try:
            return schema.model_validate_json(raw)
        except (ValidationError, ValueError) as exc:
            raise LLMError(f"structured output did not match {schema.__name__}") from exc

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"LLM request failed: {exc}") from exc
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise LLMError(f"LLM returned HTTP {response.status_code}: {response.text[:200]}")
        try:
            body: Any = response.json()
        except ValueError as exc:
            raise LLMError("LLM response body is not JSON") from exc
        if not isinstance(body, dict):
            raise LLMError("LLM response body is not an object")
        return body


def _content(body: dict[str, Any]) -> str:
    try:
        choices = body["choices"]
        message = choices[0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response has no choices[0].message") from exc
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LLMError("LLM response has no text content")
    return content


def _token_count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def build_gateway(llm_url: str | None) -> SimGateway:
    """A gateway for the scenario: the stub/self-hosted endpoint when configured, else a null one."""
    if llm_url:
        return OpenAICompatGateway(llm_url)
    return NullGateway()
