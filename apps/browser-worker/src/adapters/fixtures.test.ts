import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fixtureKey,
  fixtureModeFromEnv,
  RecordingTransport,
  ReplayTransport,
  transportForMode,
} from './fixtures.js'
import type { HttpRequest, HttpResponse, HttpTransport } from './http.js'

const ORIGIN = 'https://mock.example.invalid'
const GET_REQUEST: HttpRequest = {
  method: 'GET',
  url: `${ORIGIN}/products/offer-1`,
  timeoutMs: 1000,
}

const LIVE_RESPONSE: HttpResponse = {
  status: 200,
  headers: {
    'content-type': 'application/json',
    'set-cookie': 'session=super-secret-cookie',
    authorization: 'Bearer super-secret-token',
    cookie: 'a=super-secret-cookie',
  },
  body: '{"ok":true}',
}

describe('fixtureKey', () => {
  it('is stable for the same request and readable from the host and path', () => {
    const key = fixtureKey(GET_REQUEST)
    expect(key).toMatch(/^GET-mock\.example\.invalid_products_offer-1-[0-9a-f]{12}\.json$/)
    expect(fixtureKey({ ...GET_REQUEST })).toBe(key)
  })

  it('differs for a different body, method or URL', () => {
    const post = {
      method: 'POST' as const,
      url: GET_REQUEST.url,
      body: '{"text":"a"}',
      timeoutMs: 1,
    }
    expect(fixtureKey(post)).not.toBe(fixtureKey({ ...post, body: '{"text":"b"}' }))
    expect(fixtureKey(post)).not.toBe(fixtureKey({ ...post, method: 'GET', body: undefined }))
    expect(fixtureKey(GET_REQUEST)).not.toBe(
      fixtureKey({ ...GET_REQUEST, url: `${ORIGIN}/products/offer-2` })
    )
    expect(fixtureKey(GET_REQUEST)).not.toBe(
      fixtureKey({ ...GET_REQUEST, url: `${ORIGIN}/products/offer-1?p=2` })
    )
  })
})

describe('record and replay', () => {
  let dir: string

  beforeEach(async () => {
    dir = await mkdtemp(path.join(os.tmpdir(), 'adapter-fixtures-'))
  })

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true })
  })

  it('records a live exchange without secret headers, then replays it without the network', async () => {
    const liveRequest = vi.fn(() => Promise.resolve(LIVE_RESPONSE))
    const live: HttpTransport = { request: liveRequest }
    const recorded = await new RecordingTransport(live, dir).request(GET_REQUEST)
    expect(recorded.headers).toEqual({ 'content-type': 'application/json' })

    const files = await readdir(dir)
    expect(files).toEqual([fixtureKey(GET_REQUEST)])
    const raw = await readFile(path.join(dir, files[0] ?? ''), 'utf8')
    expect(raw).not.toContain('super-secret')
    expect(raw).not.toMatch(/set-cookie|authorization|"cookie"/i)

    const replayed = await new ReplayTransport(dir).request(GET_REQUEST)
    expect(replayed).toEqual(recorded)
    expect(liveRequest).toHaveBeenCalledTimes(1)
  })

  it('writes pretty JSON with sorted keys', async () => {
    const live: HttpTransport = { request: () => Promise.resolve(LIVE_RESPONSE) }
    await new RecordingTransport(live, dir).request(GET_REQUEST)
    const raw = await readFile(path.join(dir, fixtureKey(GET_REQUEST)), 'utf8')
    expect(raw.startsWith('{\n  "request"')).toBe(true)
    const parsed = JSON.parse(raw) as Record<string, unknown>
    expect(Object.keys(parsed)).toEqual(['request', 'response'])
    expect(raw.indexOf('"body"')).toBeLessThan(raw.indexOf('"method"'))
  })

  it('does not record failed exchanges', async () => {
    const live: HttpTransport = { request: () => Promise.reject(new Error('network down')) }
    await expect(new RecordingTransport(live, dir).request(GET_REQUEST)).rejects.toThrow(
      'network down'
    )
    expect(await readdir(dir)).toEqual([])
  })

  it('tells the developer how to re-record when a fixture is missing', async () => {
    const replay = new ReplayTransport(dir)
    const key = fixtureKey(GET_REQUEST)
    await expect(replay.request(GET_REQUEST)).rejects.toThrow(key)
    await expect(replay.request(GET_REQUEST)).rejects.toThrow('ADAPTER_FIXTURES=record')
  })
})

describe('transportForMode', () => {
  const live: HttpTransport = { request: () => Promise.reject(new Error('live not expected')) }

  it('returns the live transport, a recorder or a replayer', () => {
    expect(transportForMode('live', '/unused', live)).toBe(live)
    expect(transportForMode('record', '/unused', live)).toBeInstanceOf(RecordingTransport)
    expect(transportForMode('replay', '/unused', live)).toBeInstanceOf(ReplayTransport)
  })
})

describe('fixtureModeFromEnv', () => {
  it('defaults to replay so tests never reach the network unless asked', () => {
    expect(fixtureModeFromEnv({})).toBe('replay')
  })

  it('reads the three documented modes', () => {
    expect(fixtureModeFromEnv({ ADAPTER_FIXTURES: 'live' })).toBe('live')
    expect(fixtureModeFromEnv({ ADAPTER_FIXTURES: 'record' })).toBe('record')
    expect(fixtureModeFromEnv({ ADAPTER_FIXTURES: 'replay' })).toBe('replay')
  })

  it('rejects any other value', () => {
    expect(() => fixtureModeFromEnv({ ADAPTER_FIXTURES: 'RECORD' })).toThrow('ADAPTER_FIXTURES')
  })
})
