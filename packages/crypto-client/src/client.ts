import { sha256Hex } from './hash.js'
import { canonicalize } from './jcs.js'

export interface SigningClientOptions {
  keyId: string
  userId: string
}

interface StoredKey {
  keyId: string
  userId: string
  createdAt: string
}

const KEY_STORAGE_PREFIX = 'trato:signing:'
const ALGORITHM = { name: 'Ed25519' }

/**
 * Ed25519 signing client using WebCrypto.
 *
 * - Private keys are generated as non-exportable (extractable: false)
 * - Keys are stored in IndexedDB and never leave the device
 * - Signing requires the payload hash, not the payload itself
 *
 * Implements section 5.10.1-5.10.2 of the spec.
 */
export class SigningClient {
  private keyPair: CryptoKeyPair | null = null
  private keyId: string | null = null
  private userId: string | null = null

  /**
   * Check if Ed25519 is supported in this environment
   */
  static async isSupported(): Promise<boolean> {
    try {
      // Try to generate a test key pair
      await crypto.subtle.generateKey(ALGORITHM, false, ['sign', 'verify'])
      return true
    } catch {
      return false
    }
  }

  /**
   * Generate a new Ed25519 key pair.
   * The private key is non-exportable and stays on the device.
   *
   * @returns Public key as base64 for registration with server
   */
  async generateKey(options: SigningClientOptions): Promise<string> {
    // Check if we already have a key
    const existing = await this.loadKey(options.keyId)
    if (existing) {
      throw new Error(`Key ${options.keyId} already exists`)
    }

    // Generate new key pair
    this.keyPair = await crypto.subtle.generateKey(
      ALGORITHM,
      false, // NOT extractable - this is critical
      ['sign', 'verify']
    )

    this.keyId = options.keyId
    this.userId = options.userId

    // Store key metadata (IndexedDB stores the CryptoKey object)
    await this.storeKey(options)

    // Export public key for server registration
    const publicKeyBuffer = await crypto.subtle.exportKey('raw', this.keyPair.publicKey)
    return this.bufferToBase64(publicKeyBuffer)
  }

  /**
   * Load an existing key from storage
   */
  async loadKey(keyId: string): Promise<boolean> {
    try {
      const db = await this.openDatabase()
      const tx = db.transaction('keys', 'readonly')
      const store = tx.objectStore('keys')
      const request = store.get(keyId)

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          const result = request.result as { keyPair: CryptoKeyPair; metadata: StoredKey } | undefined
          if (result) {
            this.keyPair = result.keyPair
            this.keyId = result.metadata.keyId
            this.userId = result.metadata.userId
            resolve(true)
          } else {
            resolve(false)
          }
        }
        request.onerror = () => reject(request.error)
      })
    } catch {
      return false
    }
  }

  /**
   * Sign a payload and return signature.
   *
   * @param payload The object to sign (will be canonicalized)
   * @returns Signature info including hash and base64 signature
   */
  async sign(payload: unknown): Promise<{
    payloadHash: string
    signature: string
    keyId: string
  }> {
    if (!this.keyPair || !this.keyId) {
      throw new Error('No key loaded. Call loadKey() or generateKey() first.')
    }

    // Canonicalize and hash
    const canonical = canonicalize(payload)
    const payloadHash = await sha256Hex(canonical)

    // Sign the canonical payload (not the hash)
    const encoder = new TextEncoder()
    const signatureBuffer = await crypto.subtle.sign(ALGORITHM, this.keyPair.privateKey, encoder.encode(canonical))

    return {
      payloadHash,
      signature: this.bufferToBase64(signatureBuffer),
      keyId: this.keyId,
    }
  }

  /**
   * Verify a signature against a payload.
   * Uses the loaded public key.
   */
  async verify(payload: unknown, signature: string): Promise<boolean> {
    if (!this.keyPair) {
      throw new Error('No key loaded')
    }

    const canonical = canonicalize(payload)
    const encoder = new TextEncoder()
    const signatureBuffer = this.base64ToBuffer(signature)

    return crypto.subtle.verify(ALGORITHM, this.keyPair.publicKey, signatureBuffer, encoder.encode(canonical))
  }

  /**
   * Verify a signature using a provided public key (for server-side verification).
   */
  async verifyWithPublicKey(payload: unknown, signature: string, publicKeyBase64: string): Promise<boolean> {
    const publicKeyBuffer = this.base64ToBuffer(publicKeyBase64)
    const publicKey = await crypto.subtle.importKey('raw', publicKeyBuffer, ALGORITHM, true, ['verify'])

    const canonical = canonicalize(payload)
    const encoder = new TextEncoder()
    const signatureBuffer = this.base64ToBuffer(signature)

    return crypto.subtle.verify(ALGORITHM, publicKey, signatureBuffer, encoder.encode(canonical))
  }

  /**
   * Get the current key ID
   */
  getKeyId(): string | null {
    return this.keyId
  }

  /**
   * Check if a key is loaded
   */
  hasKey(): boolean {
    return this.keyPair !== null
  }

  private async storeKey(options: SigningClientOptions): Promise<void> {
    if (!this.keyPair) return

    const db = await this.openDatabase()
    const tx = db.transaction('keys', 'readwrite')
    const store = tx.objectStore('keys')

    const metadata: StoredKey = {
      keyId: options.keyId,
      userId: options.userId,
      createdAt: new Date().toISOString(),
    }

    store.put({ keyPair: this.keyPair, metadata }, options.keyId)

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  }

  private openDatabase(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('trato-signing', 1)

      request.onerror = () => reject(request.error)
      request.onsuccess = () => resolve(request.result)

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result
        if (!db.objectStoreNames.contains('keys')) {
          db.createObjectStore('keys')
        }
      }
    })
  }

  private bufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer)
    let binary = ''
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]!)
    }
    return btoa(binary)
  }

  private base64ToBuffer(base64: string): ArrayBuffer {
    const binary = atob(base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    return bytes.buffer
  }
}
