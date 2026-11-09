import { ApiError, asReauthRequired, problemFromResponse } from './problem'
import { getReauthHandler, useReauthStore } from './reauth'

export interface ApiRequest {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  path: Record<string, string> | undefined
  query?: Record<string, string | number | boolean | undefined | null>
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

export interface ApiClientOptions {
  /** Origin to prefix. Empty in the browser (same-origin BFF); required under Node tests. */
  baseUrl?: string
  fetch?: typeof fetch
  /** Key factory for writes; injectable so tests are deterministic. */
  newIdempotencyKey?: () => string
}

/** Public paths always go through the BFF, which owns the token (spec 5.1, ADR-202). */
export const BFF_PREFIX = '/api'

export function fillPath(template: string, params: Record<string, string> | undefined): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = params?.[name]
    if (value === undefined) throw new Error(`Missing path parameter "${name}" for ${template}`)
    return encodeURIComponent(value)
  })
}

function withQuery(url: string, query: ApiRequest['query']): string {
  if (!query) return url
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `${url}?${text}` : url
}

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = options.baseUrl ?? ''
  const doFetch = options.fetch ?? ((...args: Parameters<typeof fetch>) => fetch(...args))
  const newKey = options.newIdempotencyKey ?? (() => crypto.randomUUID())

  async function once(template: string, request: ApiRequest, idempotencyKey: string): Promise<Response> {
    const method = request.method ?? 'GET'
    const headers: Record<string, string> = { accept: 'application/json', ...request.headers }
    if (method !== 'GET') headers['idempotency-key'] ??= idempotencyKey
    let body: BodyInit | undefined
    if (request.body instanceof FormData) {
      body = request.body
    } else if (request.body !== undefined) {
      headers['content-type'] = 'application/json'
      body = JSON.stringify(request.body)
    }
    const url = withQuery(`${baseUrl}${BFF_PREFIX}${fillPath(template, request.path)}`, request.query)
    return doFetch(url, { method, headers, body, signal: request.signal, credentials: 'same-origin' })
  }

  /**
   * Performs one operation. On `428 reauth_required` it asks the registered handler to
   * reauthenticate and retries once with the SAME idempotency key (a replay is safe by contract).
   */
  async function request<T>(template: string, req: ApiRequest): Promise<T> {
    const key = newKey()
    let response = await once(template, req, key)
    if (response.status === 428) {
      const error = await problemFromResponse(response)
      const reauth = asReauthRequired(error)
      const handler = getReauthHandler()
      if (reauth === null || handler === null) throw error
      const store = useReauthStore.getState()
      store.begin(reauth.reason)
      let renewed = false
      try {
        renewed = await handler(reauth.reason)
      } finally {
        store.end()
      }
      if (!renewed) throw error
      response = await once(template, req, key)
    }
    if (!response.ok) throw await problemFromResponse(response)
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  return { request }
}

export type ApiClient = ReturnType<typeof createApiClient>

export { ApiError }
