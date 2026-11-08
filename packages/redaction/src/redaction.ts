/**
 * Shared redaction rules (TypeScript mirror of apps/orchestrator/src/apex/platform/redaction.py).
 *
 * Both implementations must agree on docs/observability/redaction-vectors.json. Change the rules in
 * both places and in the vectors in the same PR.
 *
 * - Key-based: a key is sensitive when its words (camelCase and separators split) contain a sensitive
 *   word or phrase, a `token` or `signature` word without an allowed modifier, a `minor`/`bp` word, or
 *   a financial metric name. A sensitive key's value is replaced entirely.
 * - Value-based: secret-shaped substrings are replaced wherever they appear in a string.
 * - Fail closed: an unexpected error replaces the value with `[REDACTED]` and increments
 *   `redactionStats.errors`. Nothing here throws.
 */

export const REDACTED = '[REDACTED]'
const MAX_DEPTH = 32

export const FINANCIAL_METRICS: readonly string[] = [
  'cash_balance',
  'credit_line_available',
  'credit_line_limit',
  'accounts_receivable',
  'accounts_payable',
  'revenue',
  'cogs',
  'fixed_costs',
  'payroll',
  'debt_service',
  'capex',
  'tax_reserve',
  'safety_buffer_pct',
  'payment_term_days',
]

export const FINANCIAL_KEYWORDS: readonly string[] = [
  'value_minor',
  'value_bp',
  'amount_minor',
  'iban',
  'bank_account',
  'buying_power',
  'budget',
  'envelope',
]

const SENSITIVE_PARTS = new Set([
  'password',
  'passwd',
  'pwd',
  'secret',
  'secrets',
  'credential',
  'credentials',
  'authorization',
  'cookie',
  'cookies',
  'apikey',
  'privatekey',
  'iban',
  'envelope',
  'envelopes',
  'budget',
])
const SENSITIVE_PHRASES: readonly (readonly string[])[] = [
  ['api', 'key'],
  ['private', 'key'],
  ['session', 'state'],
  ['buying', 'power'],
  ['bank', 'account'],
]
const TOKEN_MODIFIERS = new Set([
  'count',
  'counts',
  'usage',
  'limit',
  'max',
  'type',
  'ratio',
  'cost',
  'budget',
  'expires',
  'expiry',
  'ttl',
  'at',
])
const SIGNATURE_MODIFIERS = new Set([
  'status',
  'id',
  'ids',
  'hash',
  'count',
  'at',
  'version',
  'band',
  'model',
  'valid',
  'verified',
  'algorithm',
  'alg',
  'type',
])
const SUFFIX_PARTS = new Set(['minor', 'bp'])
const FINANCIAL_PHRASES: readonly (readonly string[])[] = [
  ...FINANCIAL_METRICS,
  ...FINANCIAL_KEYWORDS,
].map((metric) => metric.split('_'))

const KEYWORD_ALTERNATION = [
  'password',
  'passwd',
  'secret',
  'token',
  'api[_-]?key',
  'authorization',
  'cookie',
  'credential',
  'private[_-]?key',
  'session[_-]?state',
  'bank[_-]?account',
  'buying[_-]?power',
  'budget',
  'envelope',
  ...FINANCIAL_METRICS,
  ...FINANCIAL_KEYWORDS,
].join('|')

const VALUE_PATTERNS: readonly { pattern: RegExp; replacement: string }[] = [
  {
    pattern: /-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----/g,
    replacement: REDACTED,
  },
  { pattern: /AGE-SECRET-KEY-1[A-Z0-9]+/g, replacement: REDACTED },
  { pattern: /eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*/g, replacement: REDACTED },
  {
    pattern: /((?:authorization|set-cookie|cookie)\s*[:=]\s*)[^\r\n]+/gi,
    replacement: `$1${REDACTED}`,
  },
  { pattern: /Bearer\s+[A-Za-z0-9._~+/-]+=*/gi, replacement: REDACTED },
  { pattern: /\bhv[sbr]\.[A-Za-z0-9_-]{16,}/g, replacement: REDACTED },
  { pattern: /\bs\.[A-Za-z0-9]{24}\b/g, replacement: REDACTED },
  { pattern: /\bsk-[A-Za-z0-9_-]{16,}/g, replacement: REDACTED },
  {
    pattern: /\b[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]{4}){2,8}(?: ?[A-Z0-9]{1,4})?\b/g,
    replacement: REDACTED,
  },
  { pattern: /([A-Za-z][A-Za-z0-9+.-]*:\/\/)[^\s/@]+@/g, replacement: `$1${REDACTED}@` },
  {
    pattern: new RegExp(
      `((?:${KEYWORD_ALTERNATION})[A-Za-z0-9_.-]*["']?\\s*[=:]\\s*["']?)([^\\s"',;&}\\[\\]]+)`,
      'gi'
    ),
    replacement: `$1${REDACTED}`,
  },
]

export const redactionStats = { matches: 0, errors: 0 }

function keyParts(key: string): string[] {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((part) => part.length > 0)
}

function hasPhrase(parts: readonly string[], phrase: readonly string[]): boolean {
  for (let start = 0; start + phrase.length <= parts.length; start += 1) {
    if (phrase.every((word, offset) => parts[start + offset] === word)) {
      return true
    }
  }
  return false
}

export function isSensitiveKey(key: string): boolean {
  const parts = keyParts(key)
  if (parts.length === 0) {
    return false
  }
  const words = new Set(parts)
  if (parts.some((part) => SENSITIVE_PARTS.has(part) || SUFFIX_PARTS.has(part))) {
    return true
  }
  if (SENSITIVE_PHRASES.some((phrase) => hasPhrase(parts, phrase))) {
    return true
  }
  const hasModifier = (modifiers: Set<string>) => parts.some((part) => modifiers.has(part))
  if (words.has('token') && !hasModifier(TOKEN_MODIFIERS)) {
    return true
  }
  if ((words.has('signature') || words.has('signatures')) && !hasModifier(SIGNATURE_MODIFIERS)) {
    return true
  }
  return FINANCIAL_PHRASES.some((phrase) => hasPhrase(parts, phrase))
}

export function redactText(text: string): string {
  let result = text
  try {
    for (const { pattern, replacement } of VALUE_PATTERNS) {
      const matches = result.match(pattern)
      if (matches) {
        redactionStats.matches += matches.length
        result = result.replace(pattern, replacement)
      }
    }
    return result
  } catch {
    redactionStats.errors += 1
    return REDACTED
  }
}

function isPlainObject(value: object): value is Record<string, unknown> {
  const proto = Object.getPrototypeOf(value) as unknown
  return proto === Object.prototype || proto === null
}

export function redactValue(value: unknown, depth = 0): unknown {
  if (depth > MAX_DEPTH) {
    redactionStats.errors += 1
    return REDACTED
  }
  try {
    if (typeof value === 'string') {
      return redactText(value)
    }
    if (value instanceof Error) {
      return {
        type: value.name,
        message: redactText(value.message),
        stack: redactText(value.stack ?? ''),
      }
    }
    if (Array.isArray(value)) {
      return value.map((item: unknown) => redactValue(item, depth + 1))
    }
    if (value instanceof Uint8Array) {
      return redactText(new TextDecoder('utf-8').decode(value))
    }
    if (value !== null && typeof value === 'object' && isPlainObject(value)) {
      const out: Record<string, unknown> = {}
      for (const [key, item] of Object.entries(value)) {
        if (isSensitiveKey(key)) {
          redactionStats.matches += 1
          out[key] = REDACTED
        } else {
          out[key] = redactValue(item, depth + 1)
        }
      }
      return out
    }
    return value
  } catch {
    redactionStats.errors += 1
    return REDACTED
  }
}

export function redactAttributes(attributes: Record<string, unknown>): Record<string, unknown> {
  const redacted = redactValue(attributes)
  return redacted !== null && typeof redacted === 'object' && !Array.isArray(redacted)
    ? (redacted as Record<string, unknown>)
    : {}
}
