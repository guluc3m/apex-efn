/**
 * JSON Canonicalization Scheme (RFC 8785)
 *
 * Produces deterministic JSON output for signing.
 * - Object keys sorted lexicographically
 * - No whitespace
 * - Numbers in minimal form
 */

export function canonicalize(obj: unknown): string {
  return JSON.stringify(sortKeys(obj))
}

function sortKeys(obj: unknown): unknown {
  if (obj === null || obj === undefined) {
    return obj
  }

  if (Array.isArray(obj)) {
    return obj.map(sortKeys)
  }

  if (typeof obj === 'object') {
    const sorted: Record<string, unknown> = {}
    const keys = Object.keys(obj).sort()
    for (const key of keys) {
      sorted[key] = sortKeys((obj as Record<string, unknown>)[key])
    }
    return sorted
  }

  return obj
}
