/**
 * Recorded HTTP fixtures for adapter tests. Record only from approved platforms or the mock marketplace, never from
 * authenticated pages. Recorded files are committed, so they must hold no credentials and no personal data.
 */
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

import { z } from 'zod'

import type { HttpRequest, HttpResponse, HttpTransport } from './http.js'

export type FixtureMode = 'live' | 'record' | 'replay'

/** Headers that must never be written to a fixture file. */
const STRIPPED_HEADERS = new Set(['set-cookie', 'authorization', 'cookie'])

const exchangeSchema = z.object({
  request: z.object({
    method: z.enum(['GET', 'POST']),
    url: z.string(),
    body: z.string().nullable(),
  }),
  response: z.object({
    status: z.number().int(),
    headers: z.record(z.string()),
    body: z.string(),
  }),
})

export function fixtureKey(req: Pick<HttpRequest, 'method' | 'url' | 'body'>): string {
  const target = new URL(req.url)
  const readable = `${target.host}${target.pathname}`.replace(/[^a-zA-Z0-9.-]+/g, '_').slice(0, 120)
  const digest = createHash('sha256')
    .update(JSON.stringify([req.method, req.url, req.body ?? null]))
    .digest('hex')
    .slice(0, 12)
  return `${req.method}-${readable}-${digest}.json`
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortKeys)
  }
  if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>
    return Object.fromEntries(
      Object.keys(record)
        .sort()
        .map((key) => [key, sortKeys(record[key])])
    )
  }
  return value
}

function withoutSecrets(headers: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headers).filter(([name]) => !STRIPPED_HEADERS.has(name.toLowerCase()))
  )
}

/** Wraps a transport and writes every successful exchange to `dir`. Replays what it stored, so both modes match. */
export class RecordingTransport implements HttpTransport {
  constructor(
    private readonly inner: HttpTransport,
    private readonly dir: string
  ) {}

  async request(req: HttpRequest): Promise<HttpResponse> {
    const live = await this.inner.request(req)
    const stored: HttpResponse = {
      status: live.status,
      headers: withoutSecrets(live.headers),
      body: live.body,
    }
    const exchange = {
      request: { method: req.method, url: req.url, body: req.body ?? null },
      response: stored,
    }
    await mkdir(this.dir, { recursive: true })
    await writeFile(
      path.join(this.dir, fixtureKey(req)),
      `${JSON.stringify(sortKeys(exchange), null, 2)}\n`
    )
    return stored
  }
}

/** Answers from recorded files only. Never touches the network. */
export class ReplayTransport implements HttpTransport {
  constructor(private readonly dir: string) {}

  async request(req: HttpRequest): Promise<HttpResponse> {
    const key = fixtureKey(req)
    let raw: string
    try {
      raw = await readFile(path.join(this.dir, key), 'utf8')
    } catch {
      throw new Error(
        `no recorded fixture "${key}" in ${this.dir}; re-record with ADAPTER_FIXTURES=record`
      )
    }
    const exchange = exchangeSchema.parse(JSON.parse(raw) as unknown)
    return exchange.response
  }
}

export function transportForMode(
  mode: FixtureMode,
  dir: string,
  live: HttpTransport
): HttpTransport {
  switch (mode) {
    case 'live':
      return live
    case 'record':
      return new RecordingTransport(live, dir)
    case 'replay':
      return new ReplayTransport(dir)
  }
}

/** Reads `ADAPTER_FIXTURES`. Unset means `replay`, so tests never reach the network by default. */
export function fixtureModeFromEnv(env: NodeJS.ProcessEnv = process.env): FixtureMode {
  const value = env.ADAPTER_FIXTURES ?? 'replay'
  if (value === 'live' || value === 'record' || value === 'replay') {
    return value
  }
  throw new Error('ADAPTER_FIXTURES must be one of: live, record, replay')
}
