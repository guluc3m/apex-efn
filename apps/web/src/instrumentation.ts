/**
 * Next.js instrumentation hook (Next 15 `register`): OpenTelemetry (service `apex-web`) and Sentry.
 *
 * Only the Node.js server runtime is set up. The edge runtime is skipped on purpose: the web app
 * runs no edge routes, and Sentry's edge setup is not needed for the BFF.
 * Sentry is initialised here, not through `withSentryConfig`, so `next.config.ts` stays unchanged.
 * Sentry events go through the shared redactor (`@apex/redaction`), like the orchestrator.
 */

import { redactValue } from '@apex/redaction'
import type { Instrumentation } from 'next'

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== 'nodejs') {
    return
  }

  const { registerOTel } = await import('@vercel/otel')
  registerOTel({ serviceName: 'apex-web' })

  const dsn = process.env.SENTRY_DSN
  if (dsn) {
    const Sentry = await import('@sentry/nextjs')
    Sentry.init({
      dsn,
      environment: process.env.APEX_ENVIRONMENT ?? 'local',
      tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? 0),
      beforeSend: (event) => redactValue(event) as typeof event,
      beforeSendTransaction: (event) => redactValue(event) as typeof event,
    })
  }
}

export const onRequestError: Instrumentation.onRequestError = async (...args) => {
  if (process.env.NEXT_RUNTIME !== 'nodejs' || !process.env.SENTRY_DSN) {
    return
  }
  const { captureRequestError } = await import('@sentry/nextjs')
  captureRequestError(...args)
}
