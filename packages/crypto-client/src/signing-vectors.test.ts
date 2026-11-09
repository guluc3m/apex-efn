// Shared signing vectors in packages/test-vectors/signing/ (D2-06, ADR-208). The orchestrator runs the same files
// in apps/orchestrator/tests/signing/test_vectors.py, so passing both means TS and Python agree byte for byte.
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { payloadHash, sha256Hex } from './hash.js'
import { CanonicalizationError, canonicalBytes, canonicalize } from './jcs.js'

interface Vector<I, E> {
  name: string
  input: I
  expected: E
}

interface VectorFile<I, E, X = never> {
  vectors: Vector<I, E>[]
  errors?: Vector<X, { error: string }>[]
}

const load = <T>(name: string): T =>
  JSON.parse(
    readFileSync(new URL(`../../test-vectors/signing/${name}`, import.meta.url), 'utf8')
  ) as T

const jcs =
  load<VectorFile<string, { canonical: string; sha256: string; utf8_hex?: string }, string>>(
    'jcs.json'
  )
const numbers =
  load<VectorFile<{ ieee754: string }, { canonical: string }, { ieee754: string }>>(
    'jcs-numbers.json'
  )
const ed25519 =
  load<
    VectorFile<{ secret_key: string; public_key: string; message: string }, { signature: string }>
  >('ed25519.json')
const signatures =
  load<
    VectorFile<
      { payload: string; secret_key: string; public_key: string },
      { canonical: string; payload_hash: string; signature: string }
    >
  >('signatures.json')

const fromHex = (hex: string): Uint8Array<ArrayBuffer> =>
  Uint8Array.from(hex.match(/../g) ?? [], (byte) => parseInt(byte, 16))
const toHex = (bytes: ArrayBuffer | Uint8Array): string =>
  Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('')
const toBase64 = (bytes: ArrayBuffer | Uint8Array): string =>
  Buffer.from(new Uint8Array(bytes)).toString('base64')
const toBase64Url = (bytes: Uint8Array): string => Buffer.from(bytes).toString('base64url')

function double(hex: string): number {
  const view = new DataView(new ArrayBuffer(8))
  view.setBigUint64(0, BigInt(`0x${hex}`))
  return view.getFloat64(0)
}

async function importKeys(secretHex: string, publicHex: string): Promise<CryptoKeyPair> {
  const jwk = { kty: 'OKP', crv: 'Ed25519', x: toBase64Url(fromHex(publicHex)) }
  const privateKey = await crypto.subtle.importKey(
    'jwk',
    { ...jwk, d: toBase64Url(fromHex(secretHex)) },
    'Ed25519',
    false,
    ['sign']
  )
  const publicKey = await crypto.subtle.importKey('raw', fromHex(publicHex), 'Ed25519', true, [
    'verify',
  ])
  return { privateKey, publicKey }
}

describe('jcs.json', () => {
  it.each(jcs.vectors.map((v) => [v.name, v] as const))('%s', async (_, vector) => {
    const value: unknown = JSON.parse(vector.input)
    expect(canonicalize(value)).toBe(vector.expected.canonical)
    const bytes = canonicalBytes(value)
    expect(await sha256Hex(bytes)).toBe(vector.expected.sha256)
    if (vector.expected.utf8_hex) expect(toHex(bytes)).toBe(vector.expected.utf8_hex)
  })

  it.each((jcs.errors ?? []).map((v) => [v.name, v] as const))('rejects: %s', (_, vector) => {
    expect(vector.expected.error).toBe('lone_surrogate')
    expect(() => canonicalize(JSON.parse(vector.input))).toThrow(/lone surrogate/)
  })
})

describe('jcs-numbers.json', () => {
  it(`serializes all ${numbers.vectors.length} numbers`, () => {
    const mismatches = numbers.vectors
      .map((v) => [v.name, canonicalize(double(v.input.ieee754)), v.expected.canonical])
      .filter(([, got, want]) => got !== want)
    expect(mismatches).toEqual([])
    expect(numbers.vectors.length).toBeGreaterThan(2000)
  })

  it.each((numbers.errors ?? []).map((v) => [v.name, v] as const))('rejects %s', (_, vector) => {
    expect(vector.expected.error).toBe('not_finite')
    expect(() => canonicalize(double(vector.input.ieee754))).toThrow(CanonicalizationError)
  })
})

describe('ed25519.json', () => {
  it.each(ed25519.vectors.map((v) => [v.name, v] as const))('%s', async (_, vector) => {
    const { secret_key, public_key, message } = vector.input
    const keys = await importKeys(secret_key, public_key)
    const data = fromHex(message)
    const signature = await crypto.subtle.sign('Ed25519', keys.privateKey, data)
    expect(toHex(signature)).toBe(vector.expected.signature)
    expect(toHex(await crypto.subtle.exportKey('raw', keys.publicKey))).toBe(public_key)
    await expect(crypto.subtle.verify('Ed25519', keys.publicKey, signature, data)).resolves.toBe(
      true
    )
    const longer = new Uint8Array([...data, 0])
    await expect(crypto.subtle.verify('Ed25519', keys.publicKey, signature, longer)).resolves.toBe(
      false
    )
  })
})

describe('signatures.json', () => {
  it.each(signatures.vectors.map((v) => [v.name, v] as const))('%s', async (_, vector) => {
    const { payload, secret_key, public_key } = vector.input
    const value: unknown = JSON.parse(payload)
    const bytes = canonicalBytes(value)
    expect(new TextDecoder().decode(bytes)).toBe(vector.expected.canonical)
    expect(await payloadHash(value)).toBe(vector.expected.payload_hash)

    const keys = await importKeys(secret_key, Buffer.from(public_key, 'base64').toString('hex'))
    expect(toBase64(await crypto.subtle.exportKey('raw', keys.publicKey))).toBe(public_key)
    const signature = await crypto.subtle.sign('Ed25519', keys.privateKey, bytes)
    expect(toBase64(signature)).toBe(vector.expected.signature)

    const expected = Buffer.from(vector.expected.signature, 'base64')
    await expect(crypto.subtle.verify('Ed25519', keys.publicKey, expected, bytes)).resolves.toBe(
      true
    )
    for (let index = 0; index < bytes.length; index += Math.max(1, Math.floor(bytes.length / 16))) {
      const tampered = new Uint8Array(bytes)
      tampered[index] = (tampered[index] ?? 0) ^ 0x01
      await expect(
        crypto.subtle.verify('Ed25519', keys.publicKey, expected, tampered)
      ).resolves.toBe(false)
    }
  })
})
