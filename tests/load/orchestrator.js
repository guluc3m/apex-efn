/**
 * Read-heavy orchestrator API (D1-10).
 *
 * Models a dashboard user browsing: health, the gate queue, one mission and one seller confidence.
 * The mission id is fixed and normally does not exist, so the mission read answers 404 — a documented
 * response. 501 means the route exists and its engine is still owned by another lane. Neither is a
 * transport failure; a 500 or a timeout is.
 *
 * Run: `bash tests/load/run-local.sh --script orchestrator.js`.
 */

import { check } from 'k6'
import http from 'k6/http'

import {
  BASE_URL,
  HEALTH_STATUSES,
  MISSION_ID,
  READ_HEADERS,
  READ_STATUSES,
  SELLER_ID,
  THRESHOLDS,
  stagesFor,
  summary,
  think,
} from './config.js'

export const options = {
  scenarios: {
    read_api: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: stagesFor('orchestrator'),
      gracefulRampDown: '10s',
    },
  },
  thresholds: THRESHOLDS,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
}

export default function () {
  checkHealth()
  checkGateQueue()
  checkMission()
  checkSellerConfidence()
  think(0.2 + Math.random() * 0.4)
}

function checkHealth() {
  const res = http.get(`${BASE_URL}/health`, {
    headers: READ_HEADERS,
    responseCallback: HEALTH_STATUSES,
    tags: { name: 'GET /health' },
  })
  check(res, {
    'health: 200': (r) => r.status === 200,
    'health: reports healthy': (r) => {
      const body = safeJson(r)
      return body !== null && body.status === 'healthy'
    },
  })
}

function checkGateQueue() {
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

function checkMission() {
  const res = http.get(`${BASE_URL}/v1/missions/${MISSION_ID}`, {
    headers: READ_HEADERS,
    responseCallback: READ_STATUSES,
    tags: { name: 'GET /v1/missions/{id}' },
  })
  check(res, {
    'mission: found, missing or not implemented': (r) =>
      r.status === 200 || r.status === 404 || r.status === 501,
    'mission: id echoed when found': (r) => {
      if (r.status !== 200) {
        return true
      }
      const body = safeJson(r)
      return body !== null && body.id === MISSION_ID
    },
  })
}

function checkSellerConfidence() {
  const res = http.get(`${BASE_URL}/v1/sellers/${SELLER_ID}/confidence`, {
    headers: READ_HEADERS,
    responseCallback: READ_STATUSES,
    tags: { name: 'GET /v1/sellers/{id}/confidence' },
  })
  check(res, {
    'seller confidence: wired or not implemented': (r) => r.status === 200 || r.status === 501,
    'seller confidence: history array when wired': (r) => {
      if (r.status !== 200) {
        return true
      }
      const body = safeJson(r)
      return body !== null && Array.isArray(body.history)
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
  return summary(data, 'orchestrator')
}
