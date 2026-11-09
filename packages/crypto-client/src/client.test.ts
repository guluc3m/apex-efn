import { describe, expect, it } from 'vitest'

import { SigningClient } from './client.js'
import { canonicalize } from './jcs.js'

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
