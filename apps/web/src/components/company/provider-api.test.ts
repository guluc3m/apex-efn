import { http, HttpResponse } from 'msw'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createApiClient } from '@/lib/api/client'
import { buildProviderPayload, createProviderApi, isValidBaseUrl } from '@/lib/api/provider'
import { server } from '@/mocks/server'

const settings = {
  base_url: 'https://api.deepseek.com',
  model: 'deepseek-chat',
  api_key_set: true,
  updated_at: '2026-11-11T10:00:00Z',
}

const ops = () =>
  createProviderApi(createApiClient({ baseUrl: 'http://bff.test', newIdempotencyKey: () => 'key-provider-1' }))

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('llm provider operations', () => {
  it('reads the settings without the key', async () => {
    server.use(http.get('*/api/v1/settings/llm-provider', () => HttpResponse.json(settings)))
    await expect(ops().get()).resolves.toEqual(settings)
  })

  it('saves without api_key when the field is empty, keeping the stored one', async () => {
    let body: unknown
    let key: string | null = null
    server.use(
      http.put('*/api/v1/settings/llm-provider', async ({ request }) => {
        body = await request.json()
        key = request.headers.get('idempotency-key')
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await ops().save(buildProviderPayload(' https://api.deepseek.com ', ' deepseek-chat ', '   '))
    expect(body).toEqual({ base_url: 'https://api.deepseek.com', model: 'deepseek-chat' })
    expect(key).toBe('key-provider-1')
  })

  it('sends a trimmed key when the user types one', async () => {
    let body: unknown
    server.use(
      http.put('*/api/v1/settings/llm-provider', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(settings)
      }),
    )
    await ops().save(buildProviderPayload('https://api.deepseek.com', 'deepseek-chat', ' sk-test '))
    expect(body).toEqual({ base_url: 'https://api.deepseek.com', model: 'deepseek-chat', api_key: 'sk-test' })
  })

  it('treats a 200 with no body as a successful save', async () => {
    server.use(http.put('*/api/v1/settings/llm-provider', () => new HttpResponse(null, { status: 200 })))
    await expect(ops().save(buildProviderPayload('https://api.deepseek.com', 'deepseek-chat', ''))).resolves.toBeUndefined()
  })

  it('clears with DELETE and accepts 204', async () => {
    let method = ''
    server.use(
      http.delete('*/api/v1/settings/llm-provider', ({ request }) => {
        method = request.method
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await expect(ops().clear()).resolves.toBeUndefined()
    expect(method).toBe('DELETE')
  })

  it('posts the connection test', async () => {
    const result = { ok: true, models: ['deepseek-chat'], error: null }
    let method = ''
    server.use(
      http.post('*/api/v1/settings/llm-provider/test', ({ request }) => {
        method = request.method
        return HttpResponse.json(result)
      }),
    )
    await expect(ops().test()).resolves.toEqual(result)
    expect(method).toBe('POST')
  })

  it('validates the base URL before saving', () => {
    expect(isValidBaseUrl('https://api.deepseek.com')).toBe(true)
    expect(isValidBaseUrl('http://localhost:8080/v1')).toBe(true)
    expect(isValidBaseUrl('api.deepseek.com')).toBe(false)
    expect(isValidBaseUrl('ftp://example.com')).toBe(false)
    expect(isValidBaseUrl('')).toBe(false)
  })
})
