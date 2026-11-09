/**
 * JSON Canonicalization Scheme, RFC 8785 (D2-06, ADR-208).
 *
 * Decisions are hashed and signed over `canonicalBytes(payload)`. The orchestrator does the same in
 * `apex/signing/jcs.py`; both pass the shared vectors in `packages/test-vectors/signing/`, byte for byte.
 *
 * Only the JSON data model is accepted: `null`, booleans, strings, finite numbers, arrays and plain objects.
 * Anything else (`undefined`, `bigint`, functions, symbols, `Date`, `Map`, class instances, sparse arrays) throws
 * `CanonicalizationError` instead of being dropped or coerced the way `JSON.stringify` would. Strings with lone
 * surrogates and non-finite numbers throw too, as RFC 8785 requires.
 */

export class CanonicalizationError extends Error {
  override name = 'CanonicalizationError'
}

const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/

/** The RFC 8785 canonical form of `value`, as text. */
export function canonicalize(value: unknown): string {
  const parts: string[] = []
  write(value, parts, '$')
  return parts.join('')
}

/** The RFC 8785 canonical form of `value`, UTF-8 encoded: the exact bytes that are hashed and signed. */
export function canonicalBytes(value: unknown): Uint8Array<ArrayBuffer> {
  return new TextEncoder().encode(canonicalize(value))
}

function write(value: unknown, out: string[], path: string): void {
  if (value === null) {
    out.push('null')
    return
  }
  switch (typeof value) {
    case 'boolean':
      out.push(value ? 'true' : 'false')
      return
    case 'string':
      out.push(serializeString(value, path))
      return
    case 'number':
      if (!Number.isFinite(value)) {
        throw new CanonicalizationError(`${path}: ${String(value)} is not a JSON number`)
      }
      // ECMAScript Number::toString is the RFC 8785 number format; JSON.stringify also turns -0 into 0.
      out.push(JSON.stringify(value))
      return
    case 'object':
      if (Array.isArray(value)) {
        writeArray(value, out, path)
      } else {
        writeObject(value, out, path)
      }
      return
    default:
      throw new CanonicalizationError(`${path}: ${typeof value} is not a JSON value`)
  }
}

function writeArray(value: readonly unknown[], out: string[], path: string): void {
  out.push('[')
  for (let index = 0; index < value.length; index++) {
    if (!(index in value)) {
      throw new CanonicalizationError(`${path}[${index}]: sparse arrays are not JSON`)
    }
    if (index) out.push(',')
    write(value[index], out, `${path}[${index}]`)
  }
  out.push(']')
}

function writeObject(value: object, out: string[], path: string): void {
  const prototype: unknown = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) {
    const tag = Object.prototype.toString.call(value)
    throw new CanonicalizationError(`${path}: ${tag} is not a plain object`)
  }
  if (Object.getOwnPropertySymbols(value).length) {
    throw new CanonicalizationError(`${path}: symbol keys are not JSON`)
  }
  // RFC 8785 §3.2.3: sort by UTF-16 code units, which is what the default sort compares. Keys are unique.
  const keys = Object.keys(value).sort((a, b) => (a < b ? -1 : 1))
  const record = value as Record<string, unknown>
  out.push('{')
  keys.forEach((key, index) => {
    if (index) out.push(',')
    out.push(serializeString(key, path), ':')
    write(record[key], out, `${path}.${key}`)
  })
  out.push('}')
}

function serializeString(value: string, path: string): string {
  if (LONE_SURROGATE.test(value)) {
    throw new CanonicalizationError(`${path}: string contains a lone surrogate`)
  }
  return JSON.stringify(value)
}
