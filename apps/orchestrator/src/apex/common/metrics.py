"""Metric instruments for the DEV-4 lane (``docs/observability/metrics.md``).

The catalogue in that document is the source of truth for names, types, units and labels; the Grafana
dashboards query exactly those names. This module creates the instruments once and exposes small helpers so
call sites do not repeat the label names.

Rules that matter here (from the catalogue):

* Labels come from **closed sets only** — platform ids, bands, roles, outcomes, causes. Never a tenant, a
  mission, an offer, an amount or a seller name: those go to traces or redacted logs.
* A value outside its closed set is emitted as ``other``, never as free text.
* Instruments are created lazily so a test that installs a meter provider after import still sees data.
"""

from __future__ import annotations

from typing import Any, Final

from opentelemetry import metrics as otel_metrics

METER_NAME: Final = "apex"
METER_VERSION: Final = "0.1.0"

# Closed label sets from the catalogue. Anything else becomes "other".
PRICE_BANDS: Final = frozenset({"within", "atypical", "implausible", "insufficient_reference"})
CONFIDENCE_BANDS: Final = frozenset({"untrusted", "low", "medium", "high", "insufficient_data"})
GATE_CAUSES: Final = frozenset(
    {
        "price_atypical",
        "price_insufficient_reference",
        "seller_low",
        "seller_insufficient_data",
        "out_of_budget",
        "stretch_above_threshold",
        "negotiator_escalated",
        "financials_stale",
        "fx_provisional",
        "dual_control_pending",
    }
)
GATE_ACTIONS: Final = frozenset({"follow", "renegotiate", "takeover", "hold", "discard"})
LLM_OUTCOMES: Final = frozenset(
    {"ok", "error", "timeout", "circuit_open", "budget_exceeded", "schema_failed"}
)
MANIPULATION_FLAGS: Final = frozenset(
    {"burst", "five_star_share", "low_verified_share", "duplicate_text", "account_creation_spike"}
)


def closed(value: str, allowed: frozenset[str]) -> str:
    """Map a value outside its closed set to ``other`` so cardinality stays bounded."""
    return value if value in allowed else "other"


class Metrics:
    """The DEV-4 instruments. One instance per meter; use :func:`get_metrics`."""

    def __init__(self, meter: Any) -> None:
        # §2 price sanity (D4-10)
        self.price_sanity_checks = meter.create_counter(
            "apex.price_sanity.checks", unit="{check}", description="Price sanity checks by band"
        )
        self.price_sanity_relative_deviation = meter.create_histogram(
            "apex.price_sanity.relative_deviation",
            unit="1",
            description="|price - median| / median, no absolute amounts",
        )
        # §3 seller confidence (D4-10)
        self.seller_confidence_assessments = meter.create_counter(
            "apex.seller_confidence.assessments",
            unit="{assessment}",
            description="Assessments by band",
        )
        self.seller_confidence_flags = meter.create_counter(
            "apex.seller_confidence.manipulation_flags",
            unit="{flag}",
            description="Manipulation flags",
        )
        self.seller_confidence_score = meter.create_histogram(
            "apex.seller_confidence.score",
            unit="{score}",
            description="Confidence score 0-100",
            explicit_bucket_boundaries_advisory=[0, 20, 25, 40, 50, 60, 75, 80, 100],
        )
        # §4 gate health (D4-11)
        self.gate_queue_depth = meter.create_gauge(
            "apex.gate.queue.depth", unit="{item}", description="Open gate items by cause"
        )
        self.gate_oldest_item_age = meter.create_gauge(
            "apex.gate.oldest_item.age",
            unit="s",
            description="Age of the oldest open item by cause",
        )
        self.gate_sla_missed = meter.create_counter(
            "apex.gate.sla.missed", unit="{item}", description="Items past their SLA"
        )
        self.gate_items_resolved = meter.create_counter(
            "apex.gate.items.resolved",
            unit="{item}",
            description="Resolved items by cause and action",
        )
        # §5 LLM health (D4-04)
        self.llm_requests = meter.create_counter(
            "apex.llm.requests",
            unit="{request}",
            description="Gateway calls by role, endpoint and outcome",
        )
        self.llm_request_duration = meter.create_histogram(
            "apex.llm.request.duration", unit="s", description="Gateway call latency"
        )
        self.llm_json_repairs = meter.create_counter(
            "apex.llm.json_repairs",
            unit="{repair}",
            description="Structured-output repair round-trips",
        )
        self.llm_tokens = meter.create_counter(
            "apex.llm.tokens", unit="{token}", description="Tokens by role and direction"
        )
        self.llm_gpu_seconds = meter.create_counter(
            "apex.llm.gpu_seconds", unit="s", description="GPU seconds for self-hosted endpoints"
        )
        self.llm_circuit_state = meter.create_gauge(
            "apex.llm.circuit.state", unit="{state}", description="0 closed, 1 half-open, 2 open"
        )


_metrics: Metrics | None = None
_override: Metrics | None = None


def get_metrics() -> Metrics:
    """The process-wide instruments. Created on first use so a provider installed later still applies."""
    if _override is not None:
        return _override
    global _metrics
    if _metrics is None:
        _metrics = Metrics(otel_metrics.get_meter(METER_NAME, METER_VERSION))
    return _metrics


def set_metrics_for_tests(instruments: Metrics | None) -> None:
    """Point :func:`get_metrics` at instruments built from a test meter provider.

    OpenTelemetry only accepts one global meter provider per process, so a test cannot install its own with
    ``set_meter_provider`` after anything else has read the global. Injecting the instruments sidesteps that.
    """
    global _override
    _override = instruments


def reset_metrics_for_tests() -> None:
    """Drop the cached instruments and any test override."""
    global _metrics, _override
    _metrics = None
    _override = None


__all__ = [
    "CONFIDENCE_BANDS",
    "GATE_ACTIONS",
    "GATE_CAUSES",
    "LLM_OUTCOMES",
    "MANIPULATION_FLAGS",
    "Metrics",
    "PRICE_BANDS",
    "closed",
    "get_metrics",
    "reset_metrics_for_tests",
    "set_metrics_for_tests",
]
