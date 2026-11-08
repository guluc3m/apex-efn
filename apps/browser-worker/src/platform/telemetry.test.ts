import { describe, expect, it } from 'vitest'

import { configFromEnv } from './telemetry.js'

describe('configFromEnv', () => {
  it('defaults to local exporters and the standard collector port', () => {
    const config = configFromEnv({})
    expect(config).toMatchObject({
      serviceName: 'apex-browser-worker',
      enabled: true,
      otlpEndpoint: 'http://localhost:4318',
      sentryDsn: undefined,
      sentryTracesSampleRate: 0,
    })
  })

  it('honours OTEL_SDK_DISABLED, DSN and sample rate', () => {
    const config = configFromEnv({
      OTEL_SDK_DISABLED: 'TRUE',
      SENTRY_DSN: 'https://key@sentry.example/1',
      SENTRY_TRACES_SAMPLE_RATE: '0.25',
    })
    expect(config.enabled).toBe(false)
    expect(config.sentryDsn).toBe('https://key@sentry.example/1')
    expect(config.sentryTracesSampleRate).toBe(0.25)
  })
})
