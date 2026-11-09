import { canonicalBytes } from './jcs.js'

/**
 * SHA-256 hashing utilities
 */

function toBytes(data: string | Uint8Array): Uint8Array<ArrayBuffer> {
  return typeof data === 'string' ? new TextEncoder().encode(data) : new Uint8Array(data)
}

/**
 * Compute SHA-256 hash and return as lowercase hex. Strings are hashed as UTF-8.
 */
export async function sha256Hex(data: string | Uint8Array): Promise<string> {
  const hashBuffer = await crypto.subtle.digest('SHA-256', toBytes(data))
  return Array.from(new Uint8Array(hashBuffer), (b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Compute SHA-256 hash and return as ArrayBuffer
 */
export async function sha256(data: string | Uint8Array): Promise<ArrayBuffer> {
  return crypto.subtle.digest('SHA-256', toBytes(data))
}

/**
 * `payload_hash` of a decision (spec §5.10.2): SHA-256 hex of the RFC 8785 canonical bytes.
 */
export async function payloadHash(payload: unknown): Promise<string> {
  return sha256Hex(canonicalBytes(payload))
}
