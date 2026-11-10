/**
 * Shared configuration for the APEX-EFN k6 load tests (task D1-10, owner DEV-1 `/tests/load/**`).
 *
 * Auth model: these tests use the **development tenant header** (`X-Tenant-Id`). The orchestrator must
 * run with `APEX_ALLOW_TENANT_HEADER=true` and must not be given a bearer token. That escape hatch is
 * opt-in, local-only, and must stay off in any shared deployment. See `README.md`.
 *
 * The thresholds below are **load thresholds** (HTTP behaviour under concurrency). They are not business
 * configuration: price bands, trust weights and approval limits live in `/config/defaults` and the DB.
 *
 * Every request declares `expectedStatuses`, so a documented answer (404 for a fixed id, 501 for a route
 * whose engine is not wired yet) is not counted as a failure. Only an *unexpected* status (500/503, or a
 * transport error) moves `http_req_failed`.
 */

import { sleep } from 'k6'
import http from 'k6/http'

export const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

/** Tenant that the dev header impersonates. `tenant-a` exists in the Keycloak/fixture seed. */
export const TENANT_ID = __ENV.K6_TENANT_ID || 'tenant-a'

/** Fixed ids for read paths. A missing mission is a 404, which is a valid response, not an outage. */
export const MISSION_ID = __ENV.K6_MISSION_ID || 'load-test-mission-not-found'
export const SELLER_ID = __ENV.K6_SELLER_ID || 'load-test-seller'
export const PLATFORM_ID = __ENV.K6_PLATFORM_ID || 'mock-a'

export const READ_HEADERS = {
  'X-Tenant-Id': TENANT_ID,
  Accept: 'application/json',
}

export const JSON_HEADERS = Object.assign({}, READ_HEADERS, {
  'Content-Type': 'application/json',
})

/**
 * Status sets. Ranges/values are passed to `http.expectedStatuses`, which feeds `http_req_failed`.
 * 404 is contextual; 501 means "route present, engine owner still pending" (D2-09/D3-06/D4-10).
 * 5xx codes that signal a real defect (500, 503, 504) are deliberately absent.
 */
export const HEALTH_STATUSES = http.expectedStatuses(200)
export const READ_STATUSES = http.expectedStatuses(200, 404, 501)
export const WRITE_STATUSES = http.expectedStatuses(
  201,
  202,
  400,
  401,
  403,
  404,
  409,
  422,
  429,
  501,
  502
)

/**
 * Load thresholds. Meaning:
 * - `http_req_failed < 1%`: fewer than one in a hundred requests may be an unexpected status or a
 *   transport error. Expected statuses (declared per request) do not count.
 * - `http_req_duration p(95) < 800ms`: 95% of requests answer within 800 ms on a developer machine.
 * - `checks > 99%`: the response-shape assertions (JSON body, documented status) hold.
 */
export const THRESHOLDS = {
  http_req_failed: ['rate<0.01'],
  http_req_duration: ['p(95)<800'],
  checks: ['rate>0.99'],
}

const LOAD_PROFILES = {
  orchestrator: [
    { duration: '30s', target: 5 },
    { duration: '1m', target: 20 },
    { duration: '30s', target: 5 },
    { duration: '10s', target: 0 },
  ],
  mission: [
    { duration: '20s', target: 2 },
    { duration: '1m', target: 6 },
    { duration: '20s', target: 0 },
  ],
  gate: [
    { duration: '20s', target: 5 },
    { duration: '1m', target: 15 },
    { duration: '20s', target: 0 },
  ],
}

const SMOKE_PROFILES = {
  orchestrator: [
    { duration: '5s', target: 2 },
    { duration: '10s', target: 3 },
    { duration: '5s', target: 0 },
  ],
  mission: [
    { duration: '5s', target: 1 },
    { duration: '10s', target: 2 },
    { duration: '5s', target: 0 },
  ],
  gate: [
    { duration: '5s', target: 2 },
    { duration: '10s', target: 3 },
    { duration: '5s', target: 0 },
  ],
}

/**
 * Ramp for one script. `K6_PROFILE=smoke` shortens it for a quick local check; the nightly workflow
 * runs the full profile. The ramp (not a constant VU count) is what exposes queueing and pool limits.
 */
export function stagesFor(script) {
  const profile = (__ENV.K6_PROFILE || 'load').toLowerCase()
  const table = profile === 'smoke' ? SMOKE_PROFILES : LOAD_PROFILES
  const stages = table[script]
  if (!stages) {
    throw new Error(`unknown load-test script profile: ${script}`)
  }
  return stages
}

/** Think time between reads, so a VU models a dashboard user instead of a benchmark loop. */
export function think(seconds) {
  sleep(seconds)
}

function metric(data, name) {
  return data.metrics && data.metrics[name] ? data.metrics[name].values : undefined
}

function fixed(value, digits) {
  if (value === undefined || value === null || isNaN(value)) {
    return 'n/a'
  }
  return Number(value).toFixed(digits)
}

/** Human-readable end-of-test summary printed to stdout (and written next to the JSON artifact). */
export function textSummary(data, scriptName) {
  const duration = metric(data, 'http_req_duration') || {}
  const failed = metric(data, 'http_req_failed') || {}
  const iterations = metric(data, 'iterations') || {}
  const checks = metric(data, 'checks') || {}
  const passes = checks.passes || 0
  const fails = checks.fails || 0
  const total = passes + fails

  return [
    '',
    `k6 summary — ${scriptName} (${BASE_URL})`,
    `  http_req_failed.......: ${fixed((failed.rate || 0) * 100, 2)}% (threshold < 1%)`,
    `  http_req_duration p95.: ${fixed(duration['p(95)'], 2)} ms (threshold < 800 ms)`,
    `  http_req_duration avg.: ${fixed(duration.avg, 2)} ms`,
    `  iterations............: ${iterations.count || 0}`,
    `  checks................: ${passes}/${total} passed, ${fails} failed`,
    '',
  ].join('\n')
}

/**
 * `handleSummary` implementation shared by every script.
 *
 * Always prints the text summary. When `K6_SUMMARY_DIR` is set (the local runner and the nightly
 * workflow set it), the full k6 data is also written as JSON plus the text summary, for artifacts.
 */
export function summary(data, scriptName) {
  const text = textSummary(data, scriptName)
  const output = { stdout: text }
  const dir = (__ENV.K6_SUMMARY_DIR || '').replace(/\/+$/, '')
  if (dir) {
    output[`${dir}/k6-${scriptName}-summary.json`] = JSON.stringify(data, null, 2)
    output[`${dir}/k6-${scriptName}-summary.txt`] = text
  }
  return output
}
