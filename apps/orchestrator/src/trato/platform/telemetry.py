"""OpenTelemetry, structlog and Sentry wiring for the orchestrator.

- Traces, metrics and logs are exported over OTLP/HTTP to the collector (`OTEL_EXPORTER_OTLP_ENDPOINT`,
  default `http://localhost:4318`). Exporters run on background threads: an unreachable collector
  never blocks or fails startup.
- Every exported span, span event and log record passes through the shared redactor
  (`trato.platform.redaction`) before leaving the process. Sentry events go through the same redactor
  in `before_send`.
- `OTEL_SDK_DISABLED=true` turns off exporters. Logs are still redacted and written to stdout.
- `setup_telemetry` is idempotent: the first call configures the process, later calls only reuse the
  handle (and instrument the app that is passed in, once).
"""

from __future__ import annotations

import atexit
import copy
import logging
import os
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TextIO

import sentry_sdk
import structlog
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace.status import Status

from trato.platform.redaction import REDACTED, redact_attributes, redact_text, redact_value, stats

if TYPE_CHECKING:
    from collections.abc import Sequence

_DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"
_FLUSH_TIMEOUT_MS = 5000
_HANDLER_TAG = "_trato_telemetry"
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
_STANDARD_RECORD_ATTRS = frozenset(
    set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}
)


class RedactingSpanExporter(SpanExporter):
    """Wraps an exporter and rebuilds every span with redacted names, attributes and events.

    This is where redaction of span data happens. The SDK does not let processors rewrite
    attributes after `set_attribute`, so the copy is made on the way out. The original span
    object is never modified.
    """

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_redact_span(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def _redact_span(span: ReadableSpan) -> ReadableSpan:
    status = span.status
    description = redact_text(status.description) if status.description else None
    return ReadableSpan(
        name=redact_text(span.name),
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=redact_attributes(dict(span.attributes or {})),
        events=[
            Event(
                name=redact_text(event.name),
                attributes=redact_attributes(dict(event.attributes or {})),
                timestamp=event.timestamp,
            )
            for event in span.events
        ],
        links=span.links,
        kind=span.kind,
        status=Status(status.status_code, description),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def _redact_record(record: logging.LogRecord) -> logging.LogRecord:
    """Redact a record in place. Runs at creation, so every handler sees redacted data."""
    try:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.getMessage())
            record.args = ()
        else:
            record.msg = redact_value(record.msg)
        if record.exc_info:
            record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        for key, value in list(record.__dict__.items()):
            if key not in _STANDARD_RECORD_ATTRS:
                record.__dict__[key] = redact_value(value)
    except Exception:
        stats.errors += 1
        record.msg = REDACTED
        record.args = ()
        record.exc_info = None
        record.exc_text = None
    return record


_BASE_RECORD_FACTORY = logging.getLogRecordFactory()


def _redacting_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    return _redact_record(_BASE_RECORD_FACTORY(*args, **kwargs))


class RedactingLoggingHandler(LoggingHandler):
    """OTel log handler. Records are already redacted by the record factory.

    The OTel handler reads `exc_info` directly, so the (redacted) traceback is moved into the
    message here instead.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if not record.exc_info:
            super().emit(record)
            return
        clone = copy.copy(record)
        clone.exc_info = None
        traceback_text = record.exc_text or ""
        if isinstance(record.msg, dict):
            clone.msg = {**record.msg, "exception": traceback_text}
        else:
            clone.msg = f"{record.msg}\n{traceback_text}"
        super().emit(clone)


def sentry_before_send(event: Any, hint: Any) -> Any:
    """Sentry `before_send` hook: the whole event payload is redacted."""
    return redact_value(event)


def sentry_before_send_transaction(event: Any, hint: Any) -> Any:
    """Sentry `before_send_transaction` hook: same redaction as errors."""
    return redact_value(event)


def _add_trace_context(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict


def _redact_event_dict(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = redact_value(event_dict)
    return redacted


def configure_logging(
    *,
    level: str = "INFO",
    stream: TextIO | None = None,
    extra_handler: logging.Handler | None = None,
) -> None:
    """Configure structlog and the stdlib root logger to emit redacted JSON.

    Safe to call more than once: handlers installed by an earlier call are removed first.
    """
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redact_event_dict,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared,
    )
    stream_handler = logging.StreamHandler(stream or sys.stdout)
    stream_handler.setFormatter(formatter)
    logging.setLogRecordFactory(_redacting_record_factory)
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_TAG, False):
            root.removeHandler(existing)
    handlers: list[logging.Handler] = [stream_handler]
    if extra_handler is not None:
        handlers.append(extra_handler)
    for handler in handlers:
        setattr(handler, _HANDLER_TAG, True)
        root.addHandler(handler)
    root.setLevel(level.upper())
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


@dataclass(frozen=True)
class TelemetryConfig:
    """Explicit telemetry configuration. `build_telemetry` never reads the environment."""

    service_name: str
    environment: str = "local"
    enabled: bool = True
    otlp_endpoint: str = _DEFAULT_OTLP_ENDPOINT
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0


@dataclass
class TelemetryHandle:
    """Owns the providers created by `build_telemetry`. Call `shutdown()` on process exit."""

    config: TelemetryConfig
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider | None
    sentry_enabled: bool

    def shutdown(self) -> None:
        self.tracer_provider.force_flush(_FLUSH_TIMEOUT_MS)
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()
        if self.logger_provider is not None:
            self.logger_provider.shutdown()
        if self.sentry_enabled:
            sentry_sdk.flush(timeout=_FLUSH_TIMEOUT_MS / 1000)


def build_telemetry(
    config: TelemetryConfig,
    *,
    span_exporter: SpanExporter | None = None,
    log_exporter: LogRecordExporter | None = None,
    log_stream: TextIO | None = None,
) -> TelemetryHandle:
    """Build providers and logging for `config` without touching OTel's global providers.

    `span_exporter` and `log_exporter` replace the OTLP exporters (tests pass in-memory ones).
    Spans are always wrapped in `RedactingSpanExporter`; log records are redacted by the handler.
    """
    resource = Resource.create(
        {"service.name": config.service_name, "deployment.environment": config.environment}
    )
    tracer_provider = TracerProvider(resource=resource)
    base = config.otlp_endpoint.rstrip("/")
    logger_provider: LoggerProvider | None = None
    extra_handler: logging.Handler | None = None
    metric_readers: list[PeriodicExportingMetricReader] = []

    if config.enabled:
        exporter = span_exporter or OTLPSpanExporter(endpoint=f"{base}/v1/traces")
        tracer_provider.add_span_processor(BatchSpanProcessor(RedactingSpanExporter(exporter)))
        metric_readers.append(
            PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"))
        )
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(log_exporter or OTLPLogExporter(endpoint=f"{base}/v1/logs"))
        )
        extra_handler = RedactingLoggingHandler(logger_provider=logger_provider)

    configure_logging(level=config.log_level, stream=log_stream, extra_handler=extra_handler)

    sentry_enabled = bool(config.sentry_dsn)
    if config.sentry_dsn:
        sentry_sdk.init(
            dsn=config.sentry_dsn,
            environment=config.environment,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            traces_sample_rate=config.sentry_traces_sample_rate,
            before_send=sentry_before_send,
            before_send_transaction=sentry_before_send_transaction,
        )

    return TelemetryHandle(
        config=config,
        tracer_provider=tracer_provider,
        meter_provider=MeterProvider(resource=resource, metric_readers=metric_readers),
        logger_provider=logger_provider,
        sentry_enabled=sentry_enabled,
    )


def config_from_env(service_name: str) -> TelemetryConfig:
    """Build a `TelemetryConfig` from the standard OTel and Sentry environment variables."""
    disabled = os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true"
    sample_rate = os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "")
    return TelemetryConfig(
        service_name=service_name,
        environment=os.environ.get("TRATO_ENVIRONMENT", "local"),
        enabled=not disabled,
        otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_OTLP_ENDPOINT),
        log_level=os.environ.get("TRATO_LOG_LEVEL", "INFO"),
        sentry_dsn=os.environ.get("SENTRY_DSN") or None,
        sentry_traces_sample_rate=float(sample_rate) if sample_rate else 0.0,
    )


_HANDLE: TelemetryHandle | None = None
_LOCK = threading.Lock()


def setup_telemetry(app: FastAPI | None = None, *, service_name: str) -> TelemetryHandle:
    """Configure the process once (from the environment) and instrument `app` if given.

    Idempotent: calling it again returns the same handle, and an already-instrumented app is not
    instrumented twice.
    """
    global _HANDLE
    with _LOCK:
        if _HANDLE is None:
            handle = build_telemetry(config_from_env(service_name))
            trace.set_tracer_provider(handle.tracer_provider)
            metrics.set_meter_provider(handle.meter_provider)
            atexit.register(handle.shutdown)
            _HANDLE = handle
        handle = _HANDLE
    if app is not None and not getattr(app, "_is_instrumented_by_opentelemetry", False):
        FastAPIInstrumentor.instrument_app(
            app, tracer_provider=handle.tracer_provider, excluded_urls="health"
        )
    return handle
