"""Criterion 29: no secret or financial value appears in logs, traces or Sentry payloads.

Every canary below sits in a position the redaction rules are meant to catch (a sensitive key,
or a known secret shape). The test fails if any canary reaches the captured output. The negative
control checks that non-sensitive values still come through, so the capture is not simply empty.
"""

import io
import json
import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from opentelemetry import trace
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from trato.platform.telemetry import (
    TelemetryConfig,
    TelemetryHandle,
    build_telemetry,
    sentry_before_send,
    sentry_before_send_transaction,
)

_UUID = uuid.uuid4().hex
CANARY_TOKEN = f"CANARY-SECRET-token-{_UUID}"
CANARY_API_KEY = f"CANARY-SECRET-key-{_UUID}"
CANARY_PASSWORD = f"CANARY-SECRET-pw-{_UUID}"
CANARY_JWT = f"eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJDQU5BUlkifQ.CANARY-SECRET-jwt-{_UUID}"
CANARY_IBAN = "ES9121000418450200051332"
CANARY_CASH = "7351984620"
CANARY_CSV_VALUE = "9182736455"
CONTROL_MISSION = "mission-control-42"

CANARIES = [
    CANARY_TOKEN,
    CANARY_API_KEY,
    CANARY_PASSWORD,
    CANARY_JWT,
    CANARY_IBAN,
    CANARY_CASH,
    CANARY_CSV_VALUE,
]


def run_scenario(handle: TelemetryHandle, buffer: io.StringIO) -> dict[str, Any]:
    """Emit realistic events carrying canaries through every channel. Returns the Sentry payload."""
    log = structlog.get_logger("trato.leak")
    log.info(
        "mission.step",
        mission_id=CONTROL_MISSION,
        api_key=CANARY_API_KEY,
        headers={"Authorization": f"Bearer {CANARY_TOKEN}"},
        iban=CANARY_IBAN,
        cash_balance=CANARY_CASH,
        csv_row={
            "metric": "cash_balance",
            "period": "2026-01",
            "value_minor": CANARY_CSV_VALUE,
            "currency": "EUR",
        },
        jwt=CANARY_JWT,
    )
    log.warning("db.connect", url=f"postgres://trato:{CANARY_PASSWORD}@db:5432/trato")
    log.info(f"paid through {CANARY_IBAN}")

    stdlib_log = logging.getLogger("uvicorn.error")
    stdlib_log.error("upstream rejected token=%s", CANARY_TOKEN)

    try:
        raise ValueError(f"login failed password={CANARY_PASSWORD}")
    except ValueError:
        log.exception("login.failed", attempt=1)

    tracer = handle.tracer_provider.get_tracer("trato.leak")
    with tracer.start_as_current_span("negotiation.send") as span:
        span.set_attribute("http.request.header.authorization", f"Bearer {CANARY_TOKEN}")
        span.set_attribute("mission.id", CONTROL_MISSION)
        span.set_attribute("cash_balance", CANARY_CASH)
        span.add_event("llm.request", {"api_key": CANARY_API_KEY, "llm.role": "negotiator"})
        span.set_status(trace.Status(trace.StatusCode.ERROR, f"password={CANARY_PASSWORD}"))
        span.record_exception(ValueError(f"api_key={CANARY_API_KEY}"))

    return sentry_before_send(
        {
            "message": f"sync failed api_key={CANARY_API_KEY}",
            "request": {
                "url": f"https://user:{CANARY_PASSWORD}@web.example/api",
                "headers": {"Authorization": f"Bearer {CANARY_TOKEN}"},
                "cookies": {"session": CANARY_TOKEN},
            },
            "extra": {"csv_row": {"value_minor": CANARY_CSV_VALUE, "metric": "revenue"}},
            "exception": {"values": [{"value": f"password={CANARY_PASSWORD}"}]},
            "breadcrumbs": {"values": [{"message": f"cash_balance={CANARY_CASH}"}]},
        },
        {},
    )


@pytest.fixture
def captured(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TelemetryHandle, InMemorySpanExporter, InMemoryLogRecordExporter, io.StringIO]]:
    # conftest disables the SDK for the whole run; this test needs the SDK providers switched on.
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    spans = InMemorySpanExporter()
    logs = InMemoryLogRecordExporter()
    buffer = io.StringIO()
    handle = build_telemetry(
        TelemetryConfig(service_name="trato-leak-test", enabled=True),
        span_exporter=spans,
        log_exporter=logs,
        log_stream=buffer,
    )
    yield handle, spans, logs, buffer
    handle.tracer_provider.shutdown()


def _span_text(spans: InMemorySpanExporter) -> str:
    rendered = []
    for span in spans.get_finished_spans():
        rendered.append(span.name)
        rendered.append(json.dumps(dict(span.attributes or {}), default=str))
        rendered.append(span.status.description or "")
        for event in span.events:
            rendered.append(event.name)
            rendered.append(json.dumps(dict(event.attributes or {}), default=str))
    return "\n".join(rendered)


def _log_record_text(logs: InMemoryLogRecordExporter) -> str:
    rendered = []
    for data in logs.get_finished_logs():
        rendered.append(json.dumps(str(data.log_record.body), default=str))
        rendered.append(json.dumps(dict(data.log_record.attributes or {}), default=str))
    return "\n".join(rendered)


def test_no_canary_in_logs_traces_or_sentry(
    captured: tuple[TelemetryHandle, InMemorySpanExporter, InMemoryLogRecordExporter, io.StringIO],
) -> None:
    handle, spans, logs, buffer = captured
    sentry_payload = run_scenario(handle, buffer)
    handle.tracer_provider.force_flush()
    handle.logger_provider.force_flush()  # type: ignore[union-attr]

    stdout_logs = buffer.getvalue()
    span_text = _span_text(spans)
    log_text = _log_record_text(logs)
    sentry_text = json.dumps(sentry_payload, default=str)

    for name, output in {
        "stdout logs": stdout_logs,
        "otel log records": log_text,
        "span attributes/events": span_text,
        "sentry payload": sentry_text,
    }.items():
        assert output, f"{name} is empty: the test would prove nothing"
        for canary in CANARIES:
            assert canary not in output, f"canary leaked into {name}"


def test_negative_control_non_sensitive_values_survive(
    captured: tuple[TelemetryHandle, InMemorySpanExporter, InMemoryLogRecordExporter, io.StringIO],
) -> None:
    handle, spans, logs, buffer = captured
    run_scenario(handle, buffer)
    handle.tracer_provider.force_flush()
    handle.logger_provider.force_flush()  # type: ignore[union-attr]

    assert CONTROL_MISSION in buffer.getvalue()
    assert CONTROL_MISSION in _log_record_text(logs)
    assert CONTROL_MISSION in _span_text(spans)
    assert "[REDACTED]" in buffer.getvalue()
    assert "[REDACTED]" in _span_text(spans)


def test_sentry_transaction_hook_redacts_too() -> None:
    event = {
        "transaction": f"GET /x?api_key={CANARY_API_KEY}",
        "extra": {"password": CANARY_PASSWORD},
    }
    rendered = json.dumps(sentry_before_send_transaction(event, {}), default=str)
    assert CANARY_API_KEY not in rendered
    assert CANARY_PASSWORD not in rendered
