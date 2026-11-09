import { getAccessToken, getDevTenantId } from './token'

/**
 * Backend-for-frontend proxy (ADR-202): auth, headers and SSE passthrough only. No business logic.
 * Everything the orchestrator decides (bands, scores, money, eligibility) is forwarded untouched.
 */

const DEFAULT_ORCHESTRATOR_URL = 'http://localhost:8000'

/** Request headers worth forwarding. The Authorization header is rebuilt server-side, never copied. */
const FORWARDED_REQUEST_HEADERS = ['accept', 'content-type', 'idempotency-key', 'last-event-id', 'if-none-match']

/** Response headers worth returning. Hop-by-hop and encoding headers are dropped on purpose. */
const FORWARDED_RESPONSE_HEADERS = ['content-type', 'etag', 'retry-after', 'location', 'cache-control', 'last-modified']

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/**
 * CSRF guard for cookie-authenticated writes: a browser always sends `Origin` on cross-origin
 * POST/PUT/PATCH/DELETE, so a mismatching host is refused. A missing `Origin` (server-to-server,
 * curl) is allowed because it cannot come from a cross-site form or fetch.
 */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get('origin')
  if (origin === null) return true
  const host = request.headers.get('x-forwarded-host') ?? request.headers.get('host') ?? new URL(request.url).host
  try {
    return new URL(origin).host === host
  } catch {
    return false
  }
}

export function orchestratorUrl(): string {
  return (process.env.ORCHESTRATOR_URL || DEFAULT_ORCHESTRATOR_URL).replace(/\/+$/, '')
}

/** Rejects segments that could escape `/v1/...` once joined (`..`, separators, empty). */
export function isSafeSegments(segments: string[]): boolean {
  return (
    segments.length > 0 &&
    segments.every((s) => s !== '' && s !== '.' && s !== '..' && !s.includes('/') && !s.includes('\\'))
  )
}

function problem(status: number, title: string, detail?: string): Response {
  return new Response(JSON.stringify({ type: 'about:blank', title, status, ...(detail ? { detail } : {}) }), {
    status,
    headers: { 'content-type': 'application/problem+json', 'cache-control': 'no-store' },
  })
}

export async function proxyToOrchestrator(
  request: Request,
  segments: string[],
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  if (!isSafeSegments(segments)) return problem(400, 'Invalid path')
  if (WRITE_METHODS.has(request.method) && !isSameOrigin(request)) return problem(403, 'Cross-origin write refused')

  const source = new URL(request.url)
  const target = `${orchestratorUrl()}/v1/${segments.map(encodeURIComponent).join('/')}${source.search}`

  const headers = new Headers()
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }

  const token = await getAccessToken()
  if (token) headers.set('authorization', `Bearer ${token}`)
  const tenant = getDevTenantId()
  if (tenant) headers.set('x-tenant-id', tenant)

  // Writes always carry an Idempotency-Key (contract). The client sends its own so a retry after a
  // 428 replays the same key; the BFF only fills the gap for callers that did not.
  if (WRITE_METHODS.has(request.method) && !headers.has('idempotency-key')) {
    headers.set('idempotency-key', crypto.randomUUID())
  }

  const hasBody = WRITE_METHODS.has(request.method)
  let upstream: Response
  try {
    upstream = await fetchImpl(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      // Aborts the upstream stream when the browser closes the SSE connection.
      signal: request.signal,
      cache: 'no-store',
    })
  } catch {
    return problem(502, 'Orchestrator unreachable', 'The orchestrator did not answer.')
  }

  const out = new Headers()
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name)
    if (value) out.set(name, value)
  }
  if (upstream.headers.get('content-type')?.startsWith('text/event-stream')) {
    out.set('cache-control', 'no-store, no-transform')
    out.set('x-accel-buffering', 'no')
  }

  // Streams the body through, so SSE events reach the browser as they are produced.
  return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: out })
}
