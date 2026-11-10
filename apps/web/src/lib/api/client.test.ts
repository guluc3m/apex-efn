import { http, HttpResponse } from 'msw'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { reauthProblemFixture } from '@/mocks/handlers'
import { server } from '@/mocks/server'

import { createApiClient } from './client'
import { createOperations } from './operations'
import { ApiError } from './problem'
import { setReauthHandler, useReauthStore } from './reauth'

const BASE = 'http://bff.test'
const ops = () => createOperations(createApiClient({ baseUrl: BASE, newIdempotencyKey: () => 'key-1' }))

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  setReauthHandler(null)
})
afterAll(() => server.close())

describe('api client', () => {
  it('returns typed data from the mocked contract routes', async () => {
    const mission = await ops().getMission('ms_42')
    expect(mission.id).toBe('ms_42')
  })

  it('sends the Idempotency-Key on writes and none on reads', async () => {
    const seen: Record<string, string | null> = {}
    server.use(
      http.post('*/api/v1/missions', ({ request }) => {
        seen.write = request.headers.get('idempotency-key')
        return HttpResponse.json({}, { status: 201 })
      }),
      http.get('*/api/v1/missions/:id', ({ request }) => {
        seen.read = request.headers.get('idempotency-key')
        return HttpResponse.json({})
      }),
    )
    await ops().createMission({ sourcing_request_id: 'sr_1' })
    await ops().getMission('ms_1')
    expect(seen).toEqual({ write: 'key-1', read: null })
  })

  it('posts the snapshot activation to the onboarding path with the import id', async () => {
    let seen: unknown
    server.use(
      http.post('*/api/v1/onboarding/ob_1/financial-csv/activate', async ({ request }) => {
        seen = await request.json()
        return HttpResponse.json({ decision_id: 'dec_1', status: 'pending_signature' }, { status: 202 })
      }),
    )
    const res = await ops().activateFinancialSnapshot('ob_1', { import_id: 'imp_1' })
    expect(seen).toEqual({ import_id: 'imp_1' })
    expect(res.decision_id).toBe('dec_1')
  })

  it('maps problem+json errors to ApiError', async () => {
    server.use(
      http.get('*/api/v1/missions/:id', () =>
        HttpResponse.json({ type: 'about:blank', title: 'Not found', status: 404 }, { status: 404 }),
      ),
    )
    await expect(ops().getMission('nope')).rejects.toMatchObject({ name: 'ApiError', status: 404 })
  })

  describe('428 reauth_required', () => {
    function expireOnce() {
      let calls = 0
      const keys: (string | null)[] = []
      server.use(
        http.post('*/api/v1/missions', ({ request }) => {
          calls += 1
          keys.push(request.headers.get('idempotency-key'))
          return calls === 1
            ? HttpResponse.json(reauthProblemFixture, { status: 428 })
            : HttpResponse.json({ id: 'ms_1' }, { status: 201 })
        }),
      )
      return { calls: () => calls, keys }
    }

    it('retries once with the same key after the handler reauthenticates', async () => {
      const spy = expireOnce()
      const reasons: string[] = []
      setReauthHandler((reason) => {
        reasons.push(reason)
        expect(useReauthStore.getState().pending).toBe(reason)
        return Promise.resolve(true)
      })
      await ops().createMission({ sourcing_request_id: 'sr_1' })
      expect(reasons).toEqual(['session_expired'])
      expect(spy.calls()).toBe(2)
      expect(spy.keys).toEqual(['key-1', 'key-1'])
      expect(useReauthStore.getState().pending).toBeNull()
    })

    it('throws when no handler is registered and never retries silently', async () => {
      const spy = expireOnce()
      await expect(ops().createMission({ sourcing_request_id: 'sr_1' })).rejects.toMatchObject({ status: 428 })
      expect(spy.calls()).toBe(1)
    })

    it('throws the 428 when the user does not reauthenticate', async () => {
      const spy = expireOnce()
      setReauthHandler(() => Promise.resolve(false))
      await expect(ops().createMission({ sourcing_request_id: 'sr_1' })).rejects.toBeInstanceOf(ApiError)
      expect(spy.calls()).toBe(1)
    })

    it('does not loop when the retry is rejected with 428 again', async () => {
      let calls = 0
      server.use(
        http.post('*/api/v1/missions', () => {
          calls += 1
          return HttpResponse.json(reauthProblemFixture, { status: 428 })
        }),
      )
      setReauthHandler(() => Promise.resolve(true))
      await expect(ops().createMission({ sourcing_request_id: 'sr_1' })).rejects.toMatchObject({ status: 428 })
      expect(calls).toBe(2)
    })
  })
})
