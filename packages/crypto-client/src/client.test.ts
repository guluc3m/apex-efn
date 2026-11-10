import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Ed25519UnsupportedError, SigningClient } from './client.js'
import { sha256Hex } from './hash.js'
import { canonicalBytes, canonicalize } from './jcs.js'

function toBase64(buffer: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
}

async function signPayload(payload: unknown) {
  const keys = await crypto.subtle.generateKey({ name: 'Ed25519' }, false, ['sign', 'verify'])
  const data = new TextEncoder().encode(canonicalize(payload))
  const signature = await crypto.subtle.sign({ name: 'Ed25519' }, keys.privateKey, data)
  const publicKey = await crypto.subtle.exportKey('raw', keys.publicKey)
  return { signature: toBase64(signature), publicKey: toBase64(publicKey) }
}

describe('SigningClient.verifyWithPublicKey', () => {
  const client = new SigningClient()
  const decision = { offerId: 'o1', amountMinor: 1000, action: 'approve' }

  it('accepts a valid signature regardless of key order', async () => {
    const { signature, publicKey } = await signPayload(decision)
    const reordered = { action: 'approve', amountMinor: 1000, offerId: 'o1' }
    await expect(client.verifyWithPublicKey(reordered, signature, publicKey)).resolves.toBe(true)
  })

  it('rejects a tampered payload', async () => {
    const { signature, publicKey } = await signPayload(decision)
    const tampered = { ...decision, amountMinor: 1 }
    await expect(client.verifyWithPublicKey(tampered, signature, publicKey)).resolves.toBe(false)
  })

  it('rejects a signature from another key', async () => {
    const { signature } = await signPayload(decision)
    const { publicKey: otherKey } = await signPayload(decision)
    await expect(client.verifyWithPublicKey(decision, signature, otherKey)).resolves.toBe(false)
  })
})

describe('SigningClient enrollment and storage', () => {
  beforeEach(async () => {
    const { IDBFactory } = await import('fake-indexeddb')
    vi.stubGlobal('indexedDB', new IDBFactory())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('keeps a non-exportable key across clients and signs the canonical payload', async () => {
    const enrolling = new SigningClient()
    const publicKey = await enrolling.generateKey()
    expect(atob(publicKey)).toHaveLength(32)
    await enrolling.persist('user-1', 'key-1')

    const later = new SigningClient()
    await expect(later.load('user-2')).resolves.toBe(false)
    await expect(later.load('user-1')).resolves.toBe(true)
    const payload = { b: 1, a: 'x' }
    const signed = await later.sign(payload)
    expect(signed.keyId).toBe('key-1')
    expect(signed.payloadHash).toBe(await sha256Hex(canonicalBytes(payload)))
    await expect(
      later.verifyWithPublicKey({ a: 'x', b: 1 }, signed.signature, publicKey)
    ).resolves.toBe(true)

    await later.forget('user-1')
    await expect(new SigningClient().load('user-1')).resolves.toBe(false)
  })

  it('never lets the private key be exported', async () => {
    const client = new SigningClient()
    await client.generateKey()
    await client.persist('user-1', 'key-1')
    const stored = await new Promise<{ keyPair: CryptoKeyPair }>((resolve) => {
      const open = indexedDB.open('apex-signing')
      open.onsuccess = () => {
        const get = open.result.transaction('keys').objectStore('keys').get('user-1')
        get.onsuccess = () => resolve(get.result as { keyPair: CryptoKeyPair })
      }
    })
    expect(stored.keyPair.privateKey.extractable).toBe(false)
    await expect(crypto.subtle.exportKey('pkcs8', stored.keyPair.privateKey)).rejects.toThrow()
  })

  it('blocks signing with a clear error when Ed25519 is unavailable', async () => {
    vi.spyOn(crypto.subtle, 'generateKey').mockRejectedValue(new DOMException('NotSupportedError'))
    await expect(SigningClient.isSupported()).resolves.toBe(false)
    await expect(new SigningClient().generateKey()).rejects.toBeInstanceOf(Ed25519UnsupportedError)
    await expect(new SigningClient().sign({})).rejects.toThrow('No key loaded')
  })
})
