/**
 * Gate queue and deals dashboard under load (D1-10).
 *
 * Reads the two screens a buyer refreshes while a human decision is pending: the gate queue and the
 * deals dashboard with the filters the contract defines (`price_band`, `verdict`, `platform`,
 * `signature_status`).
 *
 * Signed actions are deliberately **not** exercised here. `POST /v1/gate/queue/{id}/actions` and
 * `POST /v1/dashboard/deals/{id}/actions` create a decision that must be signed by a human key
 * (D2-09), so a load test cannot drive them without forging a signature. Forging one would defeat the
 * audit chain the platform exists to protect. Those paths are covered by the API tests with a
 * decision-port double, and by the Playwright E2E with a virtual authenticator (D6-08). There is no
 * read-only variant of a signed action, so this script stays read-only.
 *
 * Run: `bash tests/load/run-local.sh --script gate-queue.js`.
 */

import { check } from 'k6'
import http from 'k6/http'

import {
  BASE_URL,
  PLATFORM_ID,
  READ_HEADERS,
  READ_STATUSES,
  THRESHOLDS,
  stagesFor,
  summary,
  think,
} from './config.js'

export const options = {
  scenarios: {
    gate_queue: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: stagesFor('gate'),
      gracefulRampDown: '10s',
    },
  },
  thresholds: THRESHOLDS,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
}

/** Filter combinations the dashboard sends. Values come from the contract's query parameters. */
const DEAL_FILTERS = [
  { price_band: 'atypical' },
  { verdict: 'out_of_budget' },
  { platform: PLATFORM_ID, price_band: 'low' },
  { signature_status: 'pending' },
  { verdict: 'within_budget', price_band: 'normal', platform: 'mock-b' },
]

export default function () {
  checkQueue()
  checkDeals()
  think(0.2 + Math.random() * 0.3)
}

function checkQueue() {
  const res = http.get(`${BASE_URL}/v1/gate/queue`, {
    headers: READ_HEADERS,
    responseCallback: READ_STATUSES,
    tags: { name: 'GET /v1/gate/queue' },
  })
  check(res, {
    'gate queue: wired or not implemented': (r) => r.status === 200 || r.status === 501,
    'gate queue: items array when wired': (r) => {
      if (r.status !== 200) {
        return true
      }
      const body = safeJson(r)
      return body !== null && Array.isArray(body.items)
    },
  })
}

function checkDeals() {
  const filters = DEAL_FILTERS[__ITER % DEAL_FILTERS.length]
  const query = Object.keys(filters)
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(filters[key])}`)
    .join('&')
  const res = http.get(`${BASE_URL}/v1/dashboard/deals?${query}`, {
    headers: READ_HEADERS,
    responseCallback: READ_STATUSES,
    tags: { name: 'GET /v1/dashboard/deals' },
  })
  check(res, {
    'deals: wired or not implemented': (r) => r.status === 200 || r.status === 501,
    'deals: array when wired': (r) => {
      if (r.status !== 200) {
        return true
      }
      const body = safeJson(r)
      return body !== null && Array.isArray(body.deals)
    },
  })
}

function safeJson(res) {
  try {
    return res.json()
  } catch (_err) {
    return null
  }
}

export function handleSummary(data) {
  return summary(data, 'gate-queue')
}
