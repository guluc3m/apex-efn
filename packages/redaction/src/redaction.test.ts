import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { isSensitiveKey, REDACTED, redactAttributes, redactText, redactValue } from './redaction.js'

interface Vector {
  name: string
  input: unknown
  expected: unknown
}

const vectors = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../../../docs/observability/redaction-vectors.json', import.meta.url)),
    'utf-8'
  )
) as Vector[]

describe('shared redaction vectors (same file as the Python suite)', () => {
  it.each(vectors.map((vector) => [vector.name, vector] as const))('%s', (_name, vector) => {
    expect(redactValue(vector.input)).toEqual(vector.expected)
  })
})

describe('key rules', () => {
  it.each([
    'password',
    'DB_PASSWORD',
    'client-secret',
    'apiKey',
    'x-api-key',
    'set-cookie',
    'cash_balance',
    'iban',
  ])('treats %s as sensitive', (key) => {
    expect(isSensitiveKey(key)).toBe(true)
  })

  it.each(['mission_id', 'platform', 'offer_count', 'signature_status', 'tokens', 'metric'])(
    'treats %s as non-sensitive',
    (key) => {
      expect(isSensitiveKey(key)).toBe(false)
    }
  )
})

describe('behaviour', () => {
  it('keeps arrays and plain objects as copies', () => {
    const original = { headers: { authorization: 'Bearer abc' }, list: ['password=x'] }
    const copy = redactValue(original)
    expect(copy).toEqual({ headers: { authorization: REDACTED }, list: ['password=[REDACTED]'] })
    expect(original.headers.authorization).toBe('Bearer abc')
  })

  it('redacts Error objects into type, message and stack', () => {
    const result = redactValue(new Error('login failed: token=abc123')) as Record<string, string>
    expect(result.type).toBe('Error')
    expect(result.message).toBe('login failed: token=[REDACTED]')
    expect(result.stack).not.toContain('abc123')
  })

  it('fails closed on structures deeper than the limit', () => {
    let nested: Record<string, unknown> = { leaf: 1 }
    for (let level = 0; level < 40; level += 1) {
      nested = { child: nested }
    }
    expect(JSON.stringify(redactValue(nested))).toContain(REDACTED)
  })

  it('never throws on exotic values', () => {
    const cyclic: Record<string, unknown> = { note: 'ok' }
    cyclic.self = cyclic
    expect(() => redactValue(cyclic)).not.toThrow()
    expect(redactText('')).toBe('')
  })

  it('redactAttributes returns a copy', () => {
    const original = { authorization: 'Bearer abc', mission_id: 'm1' }
    expect(redactAttributes(original)).toEqual({ authorization: REDACTED, mission_id: 'm1' })
    expect(original.authorization).toBe('Bearer abc')
  })
})
