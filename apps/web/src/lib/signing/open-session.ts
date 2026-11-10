import type { SigningKey, SigningSession } from '@apex/shared-types/contracts'

import { useSigningSession } from '@/stores/signing-session'

/** The slice of `SigningClient` this flow needs; injectable so tests need no IndexedDB. */
export interface KeyStore {
  load(userId: string): Promise<boolean>
  generateKey(): Promise<string>
  persist(userId: string, keyId: string): Promise<void>
  readonly loadedKeyId: string | null
}

export interface OpenSessionDeps {
  keys: KeyStore
  isSupported: () => Promise<boolean>
  listKeys: () => Promise<{ items: SigningKey[] }>
  registerKey: (body: { public_key: string; alg: 'Ed25519' }) => Promise<SigningKey>
  openSession: (body: { key_id: string; device_fingerprint_ref: string }) => Promise<SigningSession>
  deviceFingerprintRef: () => string
  nowMs: () => number
}

export class SigningUnsupportedError extends Error {
  constructor() {
    super('This browser cannot create Ed25519 signing keys, so signing is blocked (ADR-203).')
  }
}

/** Generates a non-exportable key, registers its public half, and stores it on this device only after the server accepts it. */
export async function enrollKey(userId: string, d: Pick<OpenSessionDeps, 'keys' | 'isSupported' | 'registerKey'>): Promise<SigningKey> {
  if (!(await d.isSupported())) throw new SigningUnsupportedError()
  const key = await d.registerKey({ public_key: await d.keys.generateKey(), alg: 'Ed25519' })
  await d.keys.persist(userId, key.id)
  return key
}

/**
 * Opens a signing window for `userId`. Enrolls a device key first when the device has none or the
 * server no longer lists it as active. Never falls back to a server-held key (ADR-203): when the
 * browser lacks Ed25519 it throws and nothing is signed.
 */
export async function openSigningSession(userId: string, d: OpenSessionDeps): Promise<SigningSession> {
  if (!(await d.isSupported())) throw new SigningUnsupportedError()

  const registered = new Set((await d.listKeys()).items.map((k) => k.id))
  let keyId: string | undefined
  if (await d.keys.load(userId)) {
    const loaded = d.keys.loadedKeyId
    if (loaded && registered.has(loaded)) keyId = loaded
  }
  keyId ??= (await enrollKey(userId, d)).id

  const session = await d.openSession({
    key_id: keyId,
    device_fingerprint_ref: d.deviceFingerprintRef(),
  })
  useSigningSession.getState().setSession(session, d.nowMs())
  return session
}
