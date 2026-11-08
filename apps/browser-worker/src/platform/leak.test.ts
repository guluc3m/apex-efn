/**
 * Criterion 29 (worker side): no secret or financial value appears in logs, traces or Sentry payloads.
 * The canaries sit in positions the redaction rules must catch. The Python suite
 * (apps/orchestrator/tests/platform/test_leak.py) checks the orchestrator the same way.
 */

import { randomUUID } from 'node:crypto'

import { trace } from '@opentelemetry/api'
import { InMemorySpanExporter, type ReadableSpan } from '@opentelemetry/sdk-trace'
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { redactSentryEvent, startTelemetry, type TelemetryHandle } from './telemetry.js'

const UUID = randomUUID().replaceAll('-', '')
const CANARY_TOKEN = `CANARY-SECRET-token-${UUID}`
const CANARY_API_KEY = `CANARY-SECRET-key-${UUID}`
const CANARY_PASSWORD = `CANARY-SECRET-pw-${UUID}`
const CANARY_JWT = `eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJDQU5BUlkifQ.CANARY-SECRET-jwt-${UUID}`
const CANARY_IBAN = 'ES9121000418450200051332'
const CANARY_CASH = '7351984620'
const CANARY_CSV_VALUE = '9182736455'
const CONTROL_MISSION = 'mission-control-42'

const CANARIES = [
  CANARY_TOKEN,
  CANARY_API_KEY,
  CANARY_PASSWORD,
  CANARY_JWT,
  CANARY_IBAN,
  CANARY_CASH,
  CANARY_CSV_VALUE,
]

class MemoryStream {
  readonly chunks: string[] = []
  write(chunk: string): void {
    this.chunks.push(chunk)
  }
  text(): string {
    return this.chunks.join('')
  }
  clear(): void {
    this.chunks.length = 0
  }
}

function spanText(spans: ReadableSpan[]): string {
  return spans
    .map((span) =>
      JSON.stringify({
        name: span.name,
        attributes: span.attributes,
        status: span.status,
        events: span.events.map((event) => ({ name: event.name, attributes: event.attributes })),
      })
    )
    .join('\n')
}

async function runScenario(handle: TelemetryHandle) {
  const logger = handle.logger
  logger.info(
    {
      mission_id: CONTROL_MISSION,
      api_key: CANARY_API_KEY,
      headers: { Authorization: `Bearer ${CANARY_TOKEN}` },
      iban: CANARY_IBAN,
      cash_balance: CANARY_CASH,
      csv_row: { metric: 'cash_balance', period: '2026-01', value_minor: CANARY_CSV_VALUE },
      jwt: CANARY_JWT,
    },
    'mission.step'
  )
  logger.warn(`connect postgres://apex:${CANARY_PASSWORD}@db:5432/apex`)
  logger.info(`paid through ${CANARY_IBAN}`)
  logger.error({ err: new Error(`login failed password=${CANARY_PASSWORD}`) }, 'login.failed')

  const tracer = trace.getTracer('apex.leak')
  const span = tracer.startSpan('negotiation.send')
  span.setAttribute('http.request.header.authorization', `Bearer ${CANARY_TOKEN}`)
  span.setAttribute('mission.id', CONTROL_MISSION)
  span.setAttribute('cash_balance', CANARY_CASH)
  span.addEvent('llm.request', { api_key: CANARY_API_KEY, 'llm.role': 'negotiator' })
  span.setStatus({ code: 2, message: `password=${CANARY_PASSWORD}` })
  span.end()
  await handle.flush()

  return redactSentryEvent({
    message: `sync failed api_key=${CANARY_API_KEY}`,
    request: {
      url: `https://user:${CANARY_PASSWORD}@web.example/api`,
      headers: { Authorization: `Bearer ${CANARY_TOKEN}` },
      cookies: { session: CANARY_TOKEN },
    },
    extra: { csv_row: { value_minor: CANARY_CSV_VALUE, metric: 'revenue' } },
    breadcrumbs: [{ message: `cash_balance=${CANARY_CASH}` }],
  })
}

// The OTel global tracer provider can be registered once per process, so both tests share one instance.
const exporter = new InMemorySpanExporter()
const logs = new MemoryStream()
let handle: TelemetryHandle

beforeAll(() => {
  handle = startTelemetry(
    {
      serviceName: 'apex-browser-worker',
      environment: 'test',
      enabled: true,
      otlpEndpoint: 'http://127.0.0.1:9',
      logLevel: 'info',
      sentryTracesSampleRate: 0,
    },
    { spanExporter: exporter, logDestination: logs }
  )
})

beforeEach(() => {
  logs.clear()
  exporter.reset()
})

describe('leak test', () => {
  it('no canary reaches logs, spans or Sentry payloads', async () => {
    const sentryPayload = await runScenario(handle)
    await handle.flush()

    const outputs = {
      'pino logs': logs.text(),
      'span attributes/events': spanText(exporter.getFinishedSpans()),
      'sentry payload': JSON.stringify(sentryPayload),
    }
    for (const [name, output] of Object.entries(outputs)) {
      expect(output.length, `${name} is empty`).toBeGreaterThan(0)
      for (const canary of CANARIES) {
        expect(output, `canary leaked into ${name}`).not.toContain(canary)
      }
    }
  })

  it('negative control: non-sensitive values still come through', async () => {
    await runScenario(handle)
    await handle.flush()

    expect(logs.text()).toContain(CONTROL_MISSION)
    expect(logs.text()).toContain('[REDACTED]')
    expect(spanText(exporter.getFinishedSpans())).toContain(CONTROL_MISSION)
  })
})
