import io
import time

import pytest

from apex.main import app
from apex.platform.telemetry import TelemetryConfig, build_telemetry, setup_telemetry


def test_setup_telemetry_is_idempotent_and_instruments_once() -> None:
    first = setup_telemetry(app, service_name="apex-orchestrator")
    second = setup_telemetry(app, service_name="apex-orchestrator")
    assert first is second
    assert getattr(app, "_is_instrumented_by_opentelemetry", False)


def test_disabled_telemetry_still_redacts_logs() -> None:
    buffer = io.StringIO()
    handle = build_telemetry(
        TelemetryConfig(service_name="apex-test", enabled=False), log_stream=buffer
    )
    import structlog

    structlog.get_logger("apex.test").info("login", password="hunter2", mission_id="m-9")
    handle.shutdown()
    output = buffer.getvalue()
    assert "hunter2" not in output
    assert "m-9" in output


def test_unreachable_collector_never_blocks_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Loopback port 9 is closed. Export happens on background threads, so building telemetry and
    # creating spans must return immediately. (Flush and shutdown can wait for the exporter's
    # own timeout while the collector is down; that is expected and not tested here.)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    started = time.monotonic()
    handle = build_telemetry(
        TelemetryConfig(service_name="apex-test", enabled=True, otlp_endpoint="http://127.0.0.1:9"),
        log_stream=io.StringIO(),
    )
    with handle.tracer_provider.get_tracer("apex.test").start_as_current_span("startup"):
        pass
    assert time.monotonic() - started < 2
