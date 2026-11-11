import { http, HttpResponse } from 'msw'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { server } from '@/mocks/server'

import { createApiClient } from './client'
import { createOperations } from './operations'
import { ApiError } from './problem'

const ops = () => createOperations(createApiClient({ baseUrl: 'http://bff.test', newIdempotencyKey: () => 'key-approval-1' }))

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('approval operations', () => {
  it('downloads the PDF bytes for one kind', async () => {
    server.use(
      http.get('*/api/v1/approvals/:id/documents/:kind', ({ params }) =>
        HttpResponse.arrayBuffer(new TextEncoder().encode(`%PDF-${String(params.kind)}`).buffer, { headers: { 'content-type': 'application/pdf' } }),
      ),
    )
    const blob = await ops().downloadApprovalDocument('d_1', 'po')
    expect(await blob.text()).toBe('%PDF-po')
  })

  it('surfaces the closed not_signed reason', async () => {
    server.use(
      http.get('*/api/v1/approvals/:id/documents/:kind', () =>
        HttpResponse.json({ status: 409, title: 'Conflict', reason: 'not_signed' }, { status: 409, headers: { 'content-type': 'application/problem+json' } }),
      ),
    )
    await expect(ops().downloadApprovalDocument('d_1', 'po')).rejects.toMatchObject({ reason: 'not_signed' })
    await expect(ops().downloadApprovalDocument('d_1', 'po')).rejects.toBeInstanceOf(ApiError)
  })

  it('asks Finance with an Idempotency-Key', async () => {
    let key: string | null = null
    server.use(
      http.post('*/api/v1/approvals/:id/notify-finance', ({ request }) => {
        key = request.headers.get('idempotency-key')
        return HttpResponse.json({ approval_id: 'd_1', notified_at: '2026-11-09T09:00:00Z' }, { status: 202 })
      }),
    )
    expect((await ops().notifyFinanceOfApproval('d_1')).approval_id).toBe('d_1')
    expect(key).toBe('key-approval-1')
  })
})
