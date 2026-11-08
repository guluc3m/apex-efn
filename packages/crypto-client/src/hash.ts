/**
 * SHA-256 hashing utilities
 */

/**
 * Compute SHA-256 hash and return as hex string
 */
export async function sha256Hex(data: string): Promise<string> {
  const encoder = new TextEncoder()
  const dataBuffer = encoder.encode(data)
  const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Compute SHA-256 hash and return as ArrayBuffer
 */
export async function sha256(data: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder()
  const dataBuffer = encoder.encode(data)
  return crypto.subtle.digest('SHA-256', dataBuffer)
}
