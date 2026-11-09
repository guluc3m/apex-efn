"""LLMGateway — the single entry point for model access (spec §5.6).

Composition per call::

    redaction guard -> budget reserve -> fallback chain
        -> [structured ladder over resilience(retries, breaker) -> transport]
        -> accounting event -> budget commit

Only the OpenAI-compatible contract is used; switching a role between OpenAI and a self-hosted engine
changes ``base_url`` and ``model`` in config, nothing else (criterion 25).
"""

from __future__ import annotations

import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, SecretStr

from apex.common.clock import Clock, SystemClock
from apex.common.metrics import LLM_OUTCOMES, closed, get_metrics
from apex.llm.accounting import LLMEvent, LLMEventSink
from apex.llm.budget import TokenBudget, TokenBudgetExceeded, estimate_prompt_tokens
from apex.llm.config import (
    LLMRole,
    LLMRolesConfig,
    RoleConfigProvider,
    RoleEndpointConfig,
    SecretResolver,
)
from apex.llm.redaction import RedactionGuard
from apex.llm.resilience import (
    AllEndpointsUnavailableError,
    BreakerState,
    Resilience,
    Sleeper,
    run_with_fallback,
)
from apex.llm.structured import LadderStep, StructuredOutputError, StructuredResult, run_ladder
from apex.llm.transport import OpenAICompatTransport

M = TypeVar("M", bound=BaseModel)


class LLMGatewayError(Exception):
    """Base class for gateway-level failures."""


class UnknownEndpointError(LLMGatewayError):
    pass


@dataclass(frozen=True)
class ChatResult:
    content: str
    endpoint_id: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: float


@dataclass(frozen=True)
class CallContext:
    mission_id: str
    tenant_id: str
    prompt_version: str
    sensitive_values: tuple[str, ...] = ()


class LLMGateway:
    """Routes role calls through redaction, budget, fallback, resilience, and accounting."""

    def __init__(
        self,
        *,
        config_provider: RoleConfigProvider,
        secrets: SecretResolver,
        budget: TokenBudget,
        sink: LLMEventSink,
        redaction: RedactionGuard | None = None,
        clock: Clock | None = None,
        http_client_factory: Callable[[RoleEndpointConfig], httpx.AsyncClient] | None = None,
        rng: random.Random | None = None,
        sleep: Sleeper | None = None,
    ) -> None:
        self._config_provider = config_provider
        self._secrets = secrets
        self._budget = budget
        self._sink = sink
        self._redaction = redaction or RedactionGuard()
        self._clock = clock or SystemClock()
        self._http_client_factory = http_client_factory
        self._rng = rng or random.Random(0)
        self._sleep = sleep
        self._transports: dict[str, OpenAICompatTransport] = {}
        self._resilience: dict[str, Resilience] = {}

    # ----- configuration helpers -------------------------------------------------

    def _roles(self, tenant_id: str) -> LLMRolesConfig:
        return self._config_provider.llm_roles(tenant_id)

    def _endpoint(self, roles: LLMRolesConfig, endpoint_id: str) -> RoleEndpointConfig:
        if endpoint_id in roles.endpoints:
            return roles.endpoints[endpoint_id]
        for cfg in roles.roles.values():
            if cfg.endpoint_id == endpoint_id:
                return cfg
        raise UnknownEndpointError(f"unknown endpoint id: {endpoint_id}")

    def _chain(self, roles: LLMRolesConfig, role: LLMRole) -> list[RoleEndpointConfig]:
        primary = roles.endpoint_for(role)
        chain = [primary]
        for ref in primary.fallback:
            chain.append(self._endpoint(roles, ref))
        return chain

    def _transport(self, cfg: RoleEndpointConfig) -> OpenAICompatTransport:
        if cfg.endpoint_id not in self._transports:
            api_key: SecretStr | None = (
                self._secrets.resolve(cfg.api_key_ref) if cfg.api_key_ref else None
            )
            http_client = self._http_client_factory(cfg) if self._http_client_factory else None
            self._transports[cfg.endpoint_id] = OpenAICompatTransport(
                endpoint_id=cfg.endpoint_id,
                base_url=cfg.base_url,
                timeout_s=cfg.timeout_s,
                api_key=api_key,
                http_client=http_client,
            )
        return self._transports[cfg.endpoint_id]

    def _resil(self, roles: LLMRolesConfig) -> Resilience:
        key = repr(roles.resilience)
        if key not in self._resilience:
            self._resilience[key] = Resilience(
                roles.resilience, self._clock, rng=self._rng, sleep=self._sleep
            )
        return self._resilience[key]

    # ----- core call -------------------------------------------------------------

    async def _invoke_endpoint(
        self,
        cfg: RoleEndpointConfig,
        roles: LLMRolesConfig,
        messages: list[dict[str, Any]],
        extra: dict[str, Any],
        *,
        temperature: float | None,
        seed: int | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or cfg.max_output_tokens,
        }
        if seed is not None and cfg.capabilities.supports_seed:
            payload["seed"] = seed
        elif cfg.seed is not None and cfg.capabilities.supports_seed:
            payload["seed"] = cfg.seed
        payload.update(extra)
        transport = self._transport(cfg)
        return await self._resil(roles).call(
            cfg.endpoint_id,
            lambda: _call_chat(transport, payload),
        )

    def _reserve_for_chain(
        self,
        chain: list[RoleEndpointConfig],
        mission_id: str,
        estimate_base: int,
    ) -> tuple[int, int]:
        """Reserve budget for the first endpoint that fits. Returns (index_in_chain, reserved).

        ``stop`` raises :class:`TokenBudgetExceeded` on the first overflow (inside ``reserve``).
        ``degrade`` walks down the chain (big -> small) until a reservation fits; if none fits the
        call is refused with :class:`TokenBudgetExceeded` — never silently continued.
        """
        for index, cfg in enumerate(chain):
            reserved = estimate_base + cfg.max_output_tokens
            if self._budget.reserve(mission_id, reserved):
                return index, reserved
        state = self._budget.state(mission_id)
        raise TokenBudgetExceeded(
            mission_id,
            state.limit,
            estimate_base + chain[-1].max_output_tokens,
            state.committed,
        )

    async def _run_on_chain(
        self,
        role: LLMRole,
        tenant_id: str,
        mission_id: str,
        messages: list[dict[str, Any]],
        *,
        runner: Callable[[RoleEndpointConfig, LLMRolesConfig], Awaitable[Any]],
    ) -> tuple[RoleEndpointConfig, Any, float, int]:
        """Run ``runner`` over the role chain. Returns (endpoint_used, result, latency_ms, reserved).

        The budget reservation tracks the endpoint actually called: on a fallback hop the previous
        reservation is released and the next endpoint's reservation is taken.
        """
        roles = self._roles(tenant_id)
        chain = self._chain(roles, role)
        estimate_base = estimate_prompt_tokens(messages)
        index, reserved = self._reserve_for_chain(chain, mission_id, estimate_base)

        started = time.perf_counter()
        hops = chain[index:]
        # Invariant: exactly one reservation is open at a time; it is re-taken per hop and released
        # on failure. The successful hop keeps its reservation for the caller to commit.
        open_reservation = reserved
        successful_reservation = 0

        async def attempt(endpoint_id: str) -> Any:
            nonlocal open_reservation, successful_reservation
            cfg = self._endpoint(roles, endpoint_id)
            if open_reservation == 0:
                # Fallback hop: the previous hop was released when it failed; reserve for this one.
                needed = estimate_base + cfg.max_output_tokens
                if not self._budget.reserve(mission_id, needed):
                    raise TokenBudgetExceeded(
                        mission_id,
                        self._budget.state(mission_id).limit,
                        needed,
                        self._budget.state(mission_id).committed,
                    )
                open_reservation = needed
            try:
                outcome = await runner(cfg, roles)
            except Exception:
                self._budget.release(mission_id, open_reservation)
                open_reservation = 0
                raise
            successful_reservation = open_reservation
            return outcome

        try:
            endpoint_id, result = await run_with_fallback([c.endpoint_id for c in hops], attempt)
        except AllEndpointsUnavailableError:
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        used = self._endpoint(roles, endpoint_id)
        return used, result, latency_ms, successful_reservation

    async def chat(
        self,
        role: LLMRole,
        messages: list[dict[str, Any]],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        temperature: float | None = None,
        seed: int | None = None,
        max_tokens: int | None = None,
        sensitive_values: Sequence[str] = (),
    ) -> ChatResult:
        """Plain chat completion through the role's endpoint chain."""
        clean = self._redaction.check_messages(messages, sensitive_values)

        async def runner(cfg: RoleEndpointConfig, roles: LLMRolesConfig) -> dict[str, Any]:
            return await self._invoke_endpoint(
                cfg,
                roles,
                clean,
                {},
                temperature=temperature,
                seed=seed,
                max_tokens=max_tokens,
            )

        used, raw, latency_ms, reserved = await self._run_on_chain(
            role, tenant_id, mission_id, clean, runner=runner
        )
        message = raw["choices"][0]["message"]
        usage = raw.get("usage", {})
        content = str(message.get("content") or "")
        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))
        self._budget.commit(mission_id, reserved, tokens_in + tokens_out)
        self._emit(
            role,
            used,
            mission_id,
            tenant_id,
            prompt_version,
            tokens_in,
            tokens_out,
            latency_ms,
            ladder_step="",
            repair=0,
            outcome="ok",
        )
        return ChatResult(
            content=content,
            endpoint_id=used.endpoint_id,
            model=used.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )

    async def chat_structured(
        self,
        role: LLMRole,
        messages: list[dict[str, Any]],
        schema: type[M],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        temperature: float | None = None,
        seed: int | None = None,
        sensitive_values: Sequence[str] = (),
    ) -> M:
        """Structured output via the escalation ladder. Raises StructuredOutputError; never defaults."""
        clean = self._redaction.check_messages(messages, sensitive_values)
        roles = self._roles(tenant_id)
        chain = self._chain(roles, role)
        estimate_base = estimate_prompt_tokens(clean)
        started = time.perf_counter()

        # Budget picks the starting endpoint (degrade walks big -> small; stop raises on overflow).
        index, reserved = self._reserve_for_chain(chain, mission_id, estimate_base)
        cfg = chain[index]
        caps = cfg.capabilities
        open_reservation = reserved

        async def invoke(
            msgs: list[dict[str, Any]], extra: dict[str, Any]
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            raw = await self._invoke_endpoint(
                cfg,
                roles,
                msgs,
                extra,
                temperature=temperature,
                seed=seed,
                max_tokens=None,
            )
            return raw["choices"][0]["message"], raw.get("usage", {})

        try:
            result: StructuredResult = await run_ladder(
                model=schema, base_messages=clean, caps=caps, invoke=invoke
            )
        except StructuredOutputError:
            self._budget.release(mission_id, open_reservation)
            self._emit(
                role,
                cfg,
                mission_id,
                tenant_id,
                prompt_version,
                0,
                0,
                (time.perf_counter() - started) * 1000.0,
                ladder_step="failed",
                repair=0,
                outcome="error",
            )
            raise
        except Exception:
            self._budget.release(mission_id, open_reservation)
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._budget.commit(mission_id, reserved, result.prompt_tokens + result.completion_tokens)
        self._emit(
            role,
            cfg,
            mission_id,
            tenant_id,
            prompt_version,
            result.prompt_tokens,
            result.completion_tokens,
            latency_ms,
            ladder_step=result.step.value,
            repair=result.repair_attempts,
            outcome="ok",
        )
        value: M = result.value
        return value

    async def embed(
        self,
        texts: list[str],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        sensitive_values: Sequence[str] = (),
    ) -> list[list[float]]:
        for text in texts:
            self._redaction.check_text(text, sensitive_values)
        roles = self._roles(tenant_id)
        cfg = roles.endpoint_for(LLMRole.EMBEDDER)
        transport = self._transport(cfg)
        started = time.perf_counter()
        estimate = sum(len(t) for t in texts) // 3 + 1
        if not self._budget.reserve(mission_id, estimate):
            raise TokenBudgetExceeded(
                mission_id,
                self._budget.state(mission_id).limit,
                estimate,
                self._budget.state(mission_id).committed,
            )
        try:
            raw = await self._resil(roles).call(
                cfg.endpoint_id,
                lambda: _call_embeddings(transport, {"model": cfg.model, "input": texts}),
            )
        except Exception:
            self._budget.release(mission_id, estimate)
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        data = raw.get("data", [])
        vectors = [list(map(float, item["embedding"])) for item in data]
        tokens = int(raw.get("usage", {}).get("prompt_tokens", estimate))
        self._budget.commit(mission_id, estimate, tokens)
        self._emit(
            LLMRole.EMBEDDER,
            cfg,
            mission_id,
            tenant_id,
            prompt_version,
            tokens,
            0,
            latency_ms,
            ladder_step="",
            repair=0,
            outcome="ok",
        )
        return vectors

    async def list_models(self, *, tenant_id: str, role: LLMRole) -> list[str]:
        roles = self._roles(tenant_id)
        cfg = roles.endpoint_for(role)
        transport = self._transport(cfg)
        raw = await self._resil(roles).call(cfg.endpoint_id, lambda: _call_models(transport))
        return [str(item["id"]) for item in raw.get("data", [])]

    def _emit(
        self,
        role: LLMRole,
        cfg: RoleEndpointConfig,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: float,
        *,
        ladder_step: str,
        repair: int,
        outcome: str,
    ) -> None:
        cost: int | None = None
        if (
            cfg.cost_per_1k_prompt_minor is not None
            and cfg.cost_per_1k_completion_minor is not None
        ):
            cost = (
                tokens_in * cfg.cost_per_1k_prompt_minor
                + tokens_out * cfg.cost_per_1k_completion_minor
            ) // 1000
        gpu_seconds: float | None = None
        if cfg.gpu_seconds_per_1k_tokens is not None:
            gpu_seconds = (tokens_in + tokens_out) / 1000.0 * cfg.gpu_seconds_per_1k_tokens
        self._record_metrics(
            role=role,
            cfg=cfg,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            ladder_step=ladder_step,
            repair=repair,
            outcome=outcome,
            gpu_seconds=gpu_seconds,
        )
        self._sink.emit(
            LLMEvent(
                mission_id=mission_id,
                tenant_id=tenant_id,
                role=role.value,
                endpoint_id=cfg.endpoint_id,
                model=cfg.model,
                prompt_version=prompt_version,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                ladder_step=ladder_step,
                repair_attempts=repair,
                outcome=outcome,
                cost_minor=cost,
                gpu_seconds=gpu_seconds,
            )
        )

    def _record_metrics(
        self,
        *,
        role: LLMRole,
        cfg: RoleEndpointConfig,
        tokens_in: int,
        tokens_out: int,
        latency_ms: float,
        ladder_step: str,
        repair: int,
        outcome: str,
        gpu_seconds: float | None,
    ) -> None:
        """Emit the LLM health metrics (``docs/observability/metrics.md`` §5).

        Labels are the role and the endpoint id only: never the mission, the tenant or the prompt.
        """
        metrics = get_metrics()
        labels = {"role": role.value, "endpoint": cfg.endpoint_id}
        metrics.llm_requests.add(1, {**labels, "outcome": closed(outcome, LLM_OUTCOMES)})
        metrics.llm_request_duration.record(latency_ms / 1000.0, labels)
        if tokens_in:
            metrics.llm_tokens.add(tokens_in, {**labels, "direction": "input"})
        if tokens_out:
            metrics.llm_tokens.add(tokens_out, {**labels, "direction": "output"})
        if repair:
            metrics.llm_json_repairs.add(
                repair, {"role": role.value, "ladder_step": _ladder_index(ladder_step)}
            )
        if gpu_seconds:
            metrics.llm_gpu_seconds.add(gpu_seconds, {"endpoint": cfg.endpoint_id})
        # The circuit state is a gauge the catalogue wants per endpoint: 0 closed, 1 half-open, 2 open.
        metrics.llm_circuit_state.set(
            _CIRCUIT_STATE_VALUE.get(self._breaker_state_for(cfg.endpoint_id), 0),
            {"endpoint": cfg.endpoint_id},
        )

    def _breaker_state_for(self, endpoint_id: str) -> str:
        """Breaker state for an endpoint, or ``closed`` when no breaker exists yet (no call has failed)."""
        for resilience in self._resilience.values():
            breaker = resilience.breakers.get(endpoint_id)
            if breaker is not None:
                return breaker.state.value
        return BreakerState.CLOSED.value

    def tokens_used(self, mission_id: str) -> int:
        """Tokens committed for a mission so far (criterion 28). Read-only: the budget owns the number."""
        return self._budget.state(mission_id).committed

    def breaker_state(self, *, tenant_id: str, endpoint_id: str) -> str:
        """Current circuit-breaker state for an endpoint (observability and tests)."""
        roles = self._roles(tenant_id)
        return self._resil(roles).breakers.get(endpoint_id).state.value

    async def close(self) -> None:
        for transport in self._transports.values():
            await transport.aclose()
        self._transports.clear()


_CIRCUIT_STATE_VALUE: dict[str, int] = {
    BreakerState.CLOSED.value: 0,
    BreakerState.HALF_OPEN.value: 1,
    BreakerState.OPEN.value: 2,
}


def _ladder_index(ladder_step: str) -> str:
    """The catalogue labels repairs by ladder step 1-5; anything else is ``other``."""
    order = {
        LadderStep.JSON_SCHEMA.value: "1",
        LadderStep.JSON_OBJECT.value: "2",
        LadderStep.TOOL_CALL.value: "3",
        LadderStep.GUIDED.value: "4",
        LadderStep.PLAIN_REPAIR.value: "5",
    }
    return order.get(ladder_step, "other")


async def _call_chat(transport: OpenAICompatTransport, payload: dict[str, Any]) -> dict[str, Any]:
    response = await transport.chat_completions(payload)
    return response.json


async def _call_embeddings(
    transport: OpenAICompatTransport, payload: dict[str, Any]
) -> dict[str, Any]:
    response = await transport.embeddings(payload)
    return response.json


async def _call_models(transport: OpenAICompatTransport) -> dict[str, Any]:
    response = await transport.list_models()
    return response.json


__all__ = [
    "CallContext",
    "ChatResult",
    "LLMGateway",
    "LLMGatewayError",
    "UnknownEndpointError",
]
