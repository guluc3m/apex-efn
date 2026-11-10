import { sha256Hex } from './hash.js'
import { canonicalBytes } from './jcs.js'

const ALGORITHM = { name: 'Ed25519' } as const
const DB_NAME = 'apex-signing'
const STORE = 'keys'

/** Thrown when this browser has no WebCrypto Ed25519. Signing is blocked: there is no server-side fallback (ADR-203). */
export class Ed25519UnsupportedError extends Error {
  constructor() {
    super(
      'This browser cannot create Ed25519 signing keys (WebCrypto Ed25519). ' +
        'Signing is disabled on this device: update the browser or use a supported one.'
    )
    this.name = 'Ed25519UnsupportedError'
  }
}

interface StoredKey {
  keyId: string
  keyPair: CryptoKeyPair
}

export interface SignedPayload {
  keyId: string
  payloadHash: string
  signature: string
}

/**
 * Ed25519 signing in the browser (spec 5.10.1, ADR-203).
 *
 * The private key is generated non-exportable and stored as a `CryptoKey` in IndexedDB, one per user and
 * device; only the public key leaves the device. Enrollment is two steps so nothing is stored for a key the
 * server refused: `generateKey()` → POST `/v1/keys/me` with the public key → `persist(userId, serverKeyId)`.
 */
export class SigningClient {
  private keyPair: CryptoKeyPair | null = null
  private keyId: string | null = null

  /** Server id of the loaded or persisted key, or null when none is loaded. */
  get loadedKeyId(): string | null {
    return this.keyId
  }

  static async isSupported(): Promise<boolean> {
    try {
      await crypto.subtle.generateKey(ALGORITHM, false, ['sign', 'verify'])
      return true
    } catch {
      return false
    }
  }

  /** New non-exportable key pair, held in memory until `persist`. Returns the raw public key as Base64. */
  async generateKey(): Promise<string> {
    let pair: CryptoKeyPair
    try {
      pair = await crypto.subtle.generateKey(ALGORITHM, false, ['sign', 'verify'])
    } catch {
      throw new Ed25519UnsupportedError()
    }
    this.keyPair = pair
    this.keyId = null
    return toBase64(await crypto.subtle.exportKey('raw', pair.publicKey))
  }

  /** Store the generated key under `userId` with the id the server assigned. Replaces this device's old key. */
  async persist(userId: string, keyId: string): Promise<void> {
    if (!this.keyPair) throw new Error('No key generated. Call generateKey() first.')
    const record: StoredKey = { keyId, keyPair: this.keyPair }
    await withStore('readwrite', (store) => store.put(record, userId))
    this.keyId = keyId
  }

  /** Load `userId`'s key from this device. False when the device has none (enroll, or the key was lost). */
  async load(userId: string): Promise<boolean> {
    const record = (await withStore('readonly', (store) => store.get(userId))) as
      StoredKey | undefined
    if (!record) return false
    this.keyPair = record.keyPair
    this.keyId = record.keyId
    return true
  }

  /** Forget `userId`'s key on this device, for example after the server revoked it. */
  async forget(userId: string): Promise<void> {
    await withStore('readwrite', (store) => store.delete(userId))
    this.keyPair = null
    this.keyId = null
  }

  /** Sign the RFC 8785 canonical bytes of `payload` (ADR-208). Compare `payloadHash` with the server's. */
  async sign(payload: unknown): Promise<SignedPayload> {
    if (!this.keyPair || !this.keyId)
      throw new Error('No key loaded. Call load() or persist() first.')
    const canonical = canonicalBytes(payload)
    const signature = await crypto.subtle.sign(ALGORITHM, this.keyPair.privateKey, canonical)
    return {
      keyId: this.keyId,
      payloadHash: await sha256Hex(canonical),
      signature: toBase64(signature),
    }
  }

  /** Verify a signature against a Base64 raw public key, for example a historical key from `/v1/keys/me`. */
  async verifyWithPublicKey(
    payload: unknown,
    signature: string,
    publicKeyBase64: string
  ): Promise<boolean> {
    const publicKey = await crypto.subtle.importKey(
      'raw',
      fromBase64(publicKeyBase64),
      ALGORITHM,
      true,
      ['verify']
    )
    return crypto.subtle.verify(
      ALGORITHM,
      publicKey,
      fromBase64(signature),
      canonicalBytes(payload)
    )
  }

  getKeyId(): string | null {
    return this.keyId
  }
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 2)
    request.onupgradeneeded = () => {
      const db = request.result
      // v1 keyed records by a client-chosen key id; nothing enrolled with it can be used, so start clean.
      if (db.objectStoreNames.contains(STORE)) db.deleteObjectStore(STORE)
      db.createObjectStore(STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
  })
}

async function withStore(
  mode: IDBTransactionMode,
  op: (store: IDBObjectStore) => IDBRequest
): Promise<unknown> {
  const db = await openDatabase()
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode)
      const request = op(tx.objectStore(STORE))
      tx.oncomplete = () => resolve(request.result)
      tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
    })
  } finally {
    db.close()
  }
}

function toBase64(buffer: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
}

function fromBase64(base64: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
}
