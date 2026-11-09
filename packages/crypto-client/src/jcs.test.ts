import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import { payloadHash, sha256, sha256Hex } from './hash.js'
import { CanonicalizationError, canonicalize } from './jcs.js'

describe('canonicalize: accepted input', () => {
  it('sorts keys recursively and keeps array order', () => {
    expect(canonicalize({ b: 1, a: { d: [2, 1], c: null } })).toBe(
      '{"a":{"c":null,"d":[2,1]},"b":1}'
    )
  })

  it('accepts null-prototype objects', () => {
    const value = Object.assign(Object.create(null) as object, { b: 2, a: 1 })
    expect(canonicalize(value)).toBe('{"a":1,"b":2}')
  })

  it('writes -0 as 0', () => {
    expect(canonicalize([-0, 0, 1.0])).toBe('[0,0,1]')
  })

  it('hashes strings as UTF-8 and bytes as they are', async () => {
    const abc = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    await expect(sha256Hex('abc')).resolves.toBe(abc)
    await expect(sha256Hex(new Uint8Array([0x61, 0x62, 0x63]))).resolves.toBe(abc)
    const digest = await sha256('€')
    expect(digest.byteLength).toBe(32)
    await expect(sha256Hex(new Uint8Array(digest))).resolves.toHaveLength(64)
    await expect(sha256Hex('€')).resolves.toBe(await sha256Hex(new Uint8Array([0xe2, 0x82, 0xac])))
  })

  it('hashes the canonical bytes', async () => {
    await expect(payloadHash({})).resolves.toBe(
      '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
    )
    await expect(payloadHash({ b: 1, a: 2 })).resolves.toBe(await payloadHash({ a: 2, b: 1 }))
  })
})

describe('canonicalize: rejected input', () => {
  const sparse: unknown[] = [1]
  sparse[2] = 3

  it.each<[string, unknown]>([
    ['undefined', undefined],
    ['undefined member', { a: undefined }],
    ['undefined element', [undefined]],
    ['sparse array', sparse],
    ['bigint', 1n],
    ['function', () => 1],
    ['symbol', Symbol('s')],
    ['symbol key', { [Symbol('s')]: 1 }],
    ['Date', new Date(0)],
    ['Map', new Map()],
    ['boxed string', new String('x')],
    ['class instance', new (class Money {})()],
    ['NaN', NaN],
    ['Infinity', Infinity],
    ['-Infinity', -Infinity],
    ['lone high surrogate', 'a\uD800'],
    ['lone low surrogate in a key', { '\uDC00': 1 }],
  ])('%s', (_, value) => {
    expect(() => canonicalize(value)).toThrow(CanonicalizationError)
  })

  it('names the type of a non-plain object', () => {
    expect(() => canonicalize({ when: new Date(0) })).toThrow(
      /^\$\.when: \[object Date\] is not a plain object/
    )
  })

  it('names the path of the bad value', () => {
    expect(() => canonicalize({ offer: { prices: [1, 2n] } })).toThrow(
      /^\$\.offer\.prices\[1\]: bigint/
    )
  })
})

describe('canonicalize: properties', () => {
  const json = fc.jsonValue({ noUnicodeString: false })

  it('is a fixed point through JSON.parse', () => {
    fc.assert(
      fc.property(json, (value) => {
        const canonical = canonicalize(value)
        expect(canonicalize(JSON.parse(canonical))).toBe(canonical)
      }),
      { numRuns: 500 }
    )
  })

  it('does not depend on member order', () => {
    fc.assert(
      fc.property(fc.dictionary(fc.fullUnicodeString(), json, { maxKeys: 8 }), (value) => {
        const reversed = Object.fromEntries(Object.entries(value).reverse())
        expect(canonicalize(reversed)).toBe(canonicalize(value))
      }),
      { numRuns: 300 }
    )
  })

  it('round-trips every finite double exactly', () => {
    fc.assert(
      fc.property(fc.double({ noNaN: true, noDefaultInfinity: true }), (value) => {
        expect(Number(canonicalize(value))).toBe(value === 0 ? 0 : value)
      }),
      { numRuns: 2000 }
    )
  })
})
