/**
 * Mission queue under load (D1-10).
 *
 * Creates work the way the UI does: `POST /v1/sourcing-requests` (normalised by the intake model), then
 * `POST /v1/missions` with the returned id, then polls the mission. Every write carries a unique
 * `Idempotency-Key`, as the contract requires; reusing one would replay a stored response instead of
 * exercising the path (only the deliberate replay test in `apps/orchestrator/tests/api` reuses a key).
 *
 * Prerequisite: an OpenAI-compatible endpoint for the `extractor` and `planner` roles. In development
 * that is the LLM stub (`apps/llm-stub`, port 8001, already in `llm.roles`); without it the writes answer
 * 502 `llm_unavailable` and the checks fail, which is the honest signal.
 *
 * Run: `bash tests/load/run-local.sh --script mission-queue.js`.
 */

import { check } from 'k6'
import http from 'k6/http'

import {
  BASE_URL,
  JSON_HEADERS,
  READ_HEADERS,
  READ_STATUSES,
  THRESHOLDS,
  WRITE_STATUSES,
  stagesFor,
  summary,
  think,
} from './config.js'

export const options = {
  scenarios: {
    mission_queue: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: stagesFor('mission'),
      gracefulRampDown: '10s',
    },
  },
  thresholds: THRESHOLDS,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
}

const NEEDS = [
  {
    natural_language: '500 food-grade PET bottles, 500 ml, delivered to Spain',
    delivery_country: 'ES',
  },
  {
    natural_language: '200 boxes of nitrile gloves, size M, delivery in Germany',
    delivery_country: 'DE',
  },
  {
    natural_language: '1200 kraft shipping boxes 30x20x15 cm, delivered in France',
    delivery_country: 'FR',
  },
]

const POLLS = 2

export default function () {
  const sourcingId = createSourcingRequest()
  if (sourcingId === null) {
    think(1)
    return
  }
  const missionId = createMission(sourcingId)
  if (missionId !== null) {
    pollMission(missionId)
  }
  think(0.5)
}

function createSourcingRequest() {
  const payload = JSON.stringify(NEEDS[__ITER % NEEDS.length])
  const res = http.post(`${BASE_URL}/v1/sourcing-requests`, payload, {
    headers: Object.assign({}, JSON_HEADERS, { 'Idempotency-Key': idempotencyKey('sourcing') }),
    responseCallback: WRITE_STATUSES,
    tags: { name: 'POST /v1/sourcing-requests' },
  })

  const accepted = check(res, {
    // 429 is the platform's own guard: the intake ledger is keyed per tenant (`intake:<tenant>`), so a
    // long load run can exhaust `LLM_MISSION_TOKEN_BUDGET`. It is a documented answer, not a defect; the
    // nightly workflow raises the limit so the queue is exercised for the whole run.
    'sourcing: 201 created or 429 token budget guard': (r) => r.status === 201 || r.status === 429,
    'sourcing: returns an id when created': (r) => {
      if (r.status !== 201) {
        return true
      }
      const body = safeJson(r)
      return body !== null && typeof body.id === 'string' && body.id.length > 0
    },
  })
  if (!accepted || res.status !== 201) {
    return null
  }
  const body = safeJson(res)
  return body !== null && typeof body.id === 'string' ? body.id : null
}

function createMission(sourcingId) {
  const payload = JSON.stringify({ sourcing_request_id: sourcingId })
  const res = http.post(`${BASE_URL}/v1/missions`, payload, {
    headers: Object.assign({}, JSON_HEADERS, { 'Idempotency-Key': idempotencyKey('mission') }),
    responseCallback: WRITE_STATUSES,
    tags: { name: 'POST /v1/missions' },
  })

  check(res, {
    'mission: 201 created': (r) => r.status === 201,
    'mission: echoes the sourcing request': (r) => {
      if (r.status !== 201) {
        return true
      }
      const body = safeJson(r)
      return body !== null && body.sourcing_request_id === sourcingId
    },
  })
  if (res.status !== 201) {
    return null
  }
  const body = safeJson(res)
  return body !== null && typeof body.id === 'string' ? body.id : null
}

function pollMission(missionId) {
  for (let i = 0; i < POLLS; i += 1) {
    const res = http.get(`${BASE_URL}/v1/missions/${missionId}`, {
      headers: READ_HEADERS,
      responseCallback: READ_STATUSES,
      tags: { name: 'GET /v1/missions/{id} (poll)' },
    })
    check(res, {
      'mission poll: 200': (r) => r.status === 200,
      'mission poll: same mission': (r) => {
        if (r.status !== 200) {
          return true
        }
        const body = safeJson(r)
        return body !== null && body.id === missionId
      },
    })
    think(0.2)
  }
}

function idempotencyKey(kind) {
  // Unique per VU and iteration: a shared key would replay the first response for the whole run.
  return `k6-${kind}-${__VU}-${__ITER}-${Date.now()}`
}

function safeJson(res) {
  try {
    return res.json()
  } catch (_err) {
    return null
  }
}

export function handleSummary(data) {
  return summary(data, 'mission-queue')
}
