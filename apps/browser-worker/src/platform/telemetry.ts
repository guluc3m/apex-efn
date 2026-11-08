/**
 * OpenTelemetry (NodeSDK), pino and Sentry wiring for the browser worker.
 *
 * - Traces and metrics go over OTLP/HTTP to the collector. Exporters run in the background, so an
 *   unreachable collector never blocks the worker.
 * - Spans are redacted by `RedactingSpanExporter` before export. Log lines are redacted by the pino
 *   `logMethod` hook. Sentry events are redacted in `beforeSend`. All three use `@apex/redaction`,
 *   the same rules as the orchestrator.
 * - `OTEL_SDK_DISABLED=true` turns exporters off. Logs are still redacted.
 */

import { isSensitiveKey, REDACTED, redactText, redactValue } from '@apex/redaction'
import { isSpanContextValid, trace } from '@opentelemetry/api'
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics'
import { NodeSDK } from '@opentelemetry/sdk-node'
import { BatchSpanProcessor, type ReadableSpan, type SpanExporter } from '@opentelemetry/sdk-trace'
import * as Sentry from '@sentry/node'
import pino, { type DestinationStream, type Logger } from 'pino'

const DEFAULT_OTLP_ENDPOINT = 'http://localhost:4318'
const SENTRY_CLOSE_TIMEOUT_MS = 2000

export interface TelemetryConfig {
  serviceName: string
  environment: string
  enabled: boolean
  otlpEndpoint: string
  logLevel: string
  sentryDsn?: string
  sentryTracesSampleRate: number
}

export interface StartTelemetryOptions {
  spanExporter?: SpanExporter
  logDestination?: DestinationStream
}

export interface TelemetryHandle {
  logger: Logger
  flush: () => Promise<void>
  shutdown: () => Promise<void>
}

/**
 * Redacts a span in place. The span has already ended, so it is not used by the SDK any more.
 * In-place is required because SDK spans are class instances and copying would lose their methods.
 */
function redactSpanInPlace(span: ReadableSpan): void {
  const mutable = span as unknown as { name: string; attributes: Record<string, unknown> }
  mutable.name = redactText(mutable.name)
  const attributes = redactAttributesCopy(mutable.attributes)
  for (const key of Object.keys(mutable.attributes)) {
    delete mutable.attributes[key]
  }
  Object.assign(mutable.attributes, attributes)
  for (const event of span.events) {
    event.name = redactText(event.name)
    if (event.attributes) {
      const redacted = redactAttributesCopy(event.attributes)
      for (const key of Object.keys(event.attributes)) {
        delete event.attributes[key]
      }
      Object.assign(event.attributes, redacted)
    }
  }
  if (span.status.message) {
    span.status.message = redactText(span.status.message)
  }
}

function redactAttributesCopy(attributes: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(attributes)) {
    out[key] = isSensitiveKey(key) ? REDACTED : redactValue(value)
  }
  return out
}

export class RedactingSpanExporter implements SpanExporter {
  constructor(private readonly inner: SpanExporter) {}

  export(spans: ReadableSpan[], resultCallback: Parameters<SpanExporter['export']>[1]): void {
    for (const span of spans) {
      redactSpanInPlace(span)
    }
    this.inner.export(spans, resultCallback)
  }

  shutdown(): Promise<void> {
    return this.inner.shutdown()
  }

  forceFlush(): Promise<void> {
    return this.inner.forceFlush?.() ?? Promise.resolve()
  }
}

/** Sentry `beforeSend` and `beforeSendTransaction` hook: the whole event is redacted. */
export function redactSentryEvent<T>(event: T): T {
  return redactValue(event) as T
}

function redactLogArgument(argument: unknown): unknown {
  return typeof argument === 'string' ? redactText(argument) : redactValue(argument)
}

export function createLogger(options: {
  service: string
  level: string
  destination?: DestinationStream
}): Logger {
  return pino(
    {
      level: options.level,
      base: { service: options.service },
      timestamp: pino.stdTimeFunctions.isoTime,
      mixin() {
        const context = trace.getActiveSpan()?.spanContext()
        return context && isSpanContextValid(context)
          ? { trace_id: context.traceId, span_id: context.spanId }
          : {}
      },
      hooks: {
        logMethod(args, method) {
          method.apply(this, args.map(redactLogArgument) as Parameters<typeof method>)
        },
      },
    },
    options.destination
  )
}

export function configFromEnv(env: NodeJS.ProcessEnv): TelemetryConfig {
  const sampleRate = env.SENTRY_TRACES_SAMPLE_RATE
  return {
    serviceName: 'apex-browser-worker',
    environment: env.APEX_ENVIRONMENT ?? 'local',
    enabled: env.OTEL_SDK_DISABLED?.trim().toLowerCase() !== 'true',
    otlpEndpoint: env.OTEL_EXPORTER_OTLP_ENDPOINT ?? DEFAULT_OTLP_ENDPOINT,
    logLevel: env.APEX_LOG_LEVEL ?? 'info',
    sentryDsn: env.SENTRY_DSN || undefined,
    sentryTracesSampleRate: sampleRate ? Number(sampleRate) : 0,
  }
}

export function startTelemetry(
  config: TelemetryConfig,
  options: StartTelemetryOptions = {}
): TelemetryHandle {
  const logger = createLogger({
    service: config.serviceName,
    level: config.logLevel,
    destination: options.logDestination,
  })

  let sdk: NodeSDK | undefined
  if (config.enabled) {
    const base = config.otlpEndpoint.replace(/\/+$/, '')
    const exporter = options.spanExporter ?? new OTLPTraceExporter({ url: `${base}/v1/traces` })
    sdk = new NodeSDK({
      serviceName: config.serviceName,
      spanProcessors: [new BatchSpanProcessor({ exporter: new RedactingSpanExporter(exporter) })],
      metricReaders: [
        new PeriodicExportingMetricReader({
          exporter: new OTLPMetricExporter({ url: `${base}/v1/metrics` }),
        }),
      ],
      instrumentations: [],
    })
    sdk.start()
  }

  if (config.sentryDsn) {
    Sentry.init({
      dsn: config.sentryDsn,
      environment: config.environment,
      tracesSampleRate: config.sentryTracesSampleRate,
      beforeSend: redactSentryEvent,
      beforeSendTransaction: redactSentryEvent,
    })
  }

  return {
    logger,
    async flush() {
      const provider = trace.getTracerProvider() as unknown as {
        getDelegate?: () => { forceFlush?: () => Promise<void> }
      }
      await provider.getDelegate?.().forceFlush?.()
    },
    async shutdown() {
      await sdk?.shutdown()
      if (config.sentryDsn) {
        await Sentry.close(SENTRY_CLOSE_TIMEOUT_MS)
      }
    },
  }
}
