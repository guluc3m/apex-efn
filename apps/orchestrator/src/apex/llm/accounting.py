"""LLM accounting: one ``LLMEvent`` per gateway call, emitted to a sink (spec §5.6).

Events carry no prompt or completion text — only identifiers, token counts, latency, the ladder step,
repair counts, outcome and optional cost / GPU-seconds. The Langfuse sink is a shape-compatible stub: it
builds the payload but performs no network I/O in tests; the real HTTP export arrives with DEV-1 telemetry.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class LLMEvent:
    mission_id: str
    tenant_id: str
    role: str
    endpoint_id: str
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    ladder_step: str
    repair_attempts: int
    outcome: str  # ok | error | budget_stop | degraded
    cost_minor: int | None = None
    gpu_seconds: float | None = None


class LLMEventSink(Protocol):
    def emit(self, event: LLMEvent) -> None: ...


@dataclass
class InMemorySink:
    events: list[LLMEvent] = field(default_factory=list)

    def emit(self, event: LLMEvent) -> None:
        self.events.append(event)


class LangfuseSink:
    """Langfuse-shaped sink. Builds trace payloads; ``transport`` is injectable and absent in tests."""

    def __init__(self, transport: LangfuseTransport | None = None) -> None:
        self._transport = transport
        self.payloads: list[dict[str, object]] = []

    def emit(self, event: LLMEvent) -> None:
        payload: dict[str, object] = {
            "name": f"llm.{event.role}",
            "metadata": asdict(event),
            "usage": {"input": event.tokens_in, "output": event.tokens_out, "unit": "TOKENS"},
            "tags": [event.tenant_id, event.endpoint_id, event.outcome],
        }
        self.payloads.append(payload)
        if self._transport is not None:
            self._transport.send(payload)


class LangfuseTransport(Protocol):
    def send(self, payload: dict[str, object]) -> None: ...


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


@dataclass
class RollingAggregator:
    """Rolling window over recent events: latency p50/p95 per endpoint, and JSON repair rate per role."""

    window: int = 500
    _latency: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    _structured_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _repaired_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record(self, event: LLMEvent, *, structured: bool) -> None:
        series = self._latency[event.endpoint_id]
        series.append(event.latency_ms)
        if len(series) > self.window:
            del series[: len(series) - self.window]
        if structured:
            self._structured_calls[event.role] += 1
            if event.repair_attempts > 0:
                self._repaired_calls[event.role] += 1

    def latency_p50_p95(self, endpoint_id: str) -> tuple[float, float]:
        values = sorted(self._latency.get(endpoint_id, []))
        return _percentile(values, 0.5), _percentile(values, 0.95)

    def json_repair_rate(self, role: str) -> float:
        total = self._structured_calls.get(role, 0)
        if total == 0:
            return 0.0
        return self._repaired_calls.get(role, 0) / total


class AggregatingSink:
    """Sink wrapper that feeds a :class:`RollingAggregator` and forwards to an inner sink."""

    def __init__(self, inner: LLMEventSink, aggregator: RollingAggregator) -> None:
        self._inner = inner
        self.aggregator = aggregator

    def emit(self, event: LLMEvent) -> None:
        self._inner.emit(event)
        self.aggregator.record(event, structured=event.ladder_step != "")


__all__ = [
    "AggregatingSink",
    "InMemorySink",
    "LLMEvent",
    "LLMEventSink",
    "LangfuseSink",
    "LangfuseTransport",
    "RollingAggregator",
]
