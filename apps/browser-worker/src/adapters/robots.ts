/**
 * Minimal robots.txt support (RFC 9309). Adapters check every URL before requesting it (ADR-500, compliance docs).
 */
import type { Clock } from '../clock.js'
import { WorkerError } from '../errors.js'

export interface RobotsRules {
  isAllowed(pathWithQuery: string): boolean
}

interface Rule {
  allow: boolean
  pattern: string
  matcher: RegExp
}

interface Group {
  agents: string[]
  rules: Rule[]
}

const ALLOW_ALL: RobotsRules = { isAllowed: () => true }
const DISALLOW_ALL: RobotsRules = { isAllowed: () => false }

/** The product token of a User-Agent string, e.g. `APEX-EFN-bot/0.1 (+https://…)` gives `APEX-EFN-bot`. */
export function productToken(userAgent: string): string {
  return (userAgent.trim().split(/[\s/]/)[0] ?? '').toLowerCase()
}

function patternToRegExp(pattern: string): RegExp {
  const anchoredEnd = pattern.endsWith('$')
  const body = anchoredEnd ? pattern.slice(0, -1) : pattern
  const source = body
    .split('*')
    .map((part) => part.replace(/[.+?^${}()|[\]\\]/g, '\\$&'))
    .join('.*')
  return new RegExp(`^${source}${anchoredEnd ? '$' : ''}`)
}

function parseGroups(text: string): Group[] {
  const groups: Group[] = []
  let current: Group | null = null
  let sawRuleInGroup = false
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/#.*$/, '').trim()
    const separator = line.indexOf(':')
    if (separator === -1) {
      continue
    }
    const field = line.slice(0, separator).trim().toLowerCase()
    const value = line.slice(separator + 1).trim()
    if (field === 'user-agent') {
      if (current === null || sawRuleInGroup) {
        current = { agents: [], rules: [] }
        groups.push(current)
        sawRuleInGroup = false
      }
      current.agents.push(value.toLowerCase())
    } else if ((field === 'allow' || field === 'disallow') && current !== null) {
      sawRuleInGroup = true
      if (value === '') {
        continue
      }
      current.rules.push({
        allow: field === 'allow',
        pattern: value,
        matcher: patternToRegExp(value),
      })
    }
  }
  return groups
}

/**
 * The group for our product token wins. The `*` group applies only when no group names us, and groups that name
 * the same token are combined. Among matching rules the longest pattern wins, and Allow wins a tie.
 */
export function parseRobots(text: string, userAgent: string): RobotsRules {
  const token = productToken(userAgent)
  const groups = parseGroups(text)
  let selected = groups.filter((group) => group.agents.includes(token))
  if (selected.length === 0) {
    selected = groups.filter((group) => group.agents.includes('*'))
  }
  const rules = selected.flatMap((group) => group.rules)
  return {
    isAllowed(pathWithQuery: string): boolean {
      let best: Rule | null = null
      for (const rule of rules) {
        if (!rule.matcher.test(pathWithQuery)) {
          continue
        }
        if (
          best === null ||
          rule.pattern.length > best.pattern.length ||
          (rule.pattern.length === best.pattern.length && rule.allow)
        ) {
          best = rule
        }
      }
      return best === null || best.allow
    },
  }
}

export type RobotsFetch = (url: string) => Promise<{ status: number; body: string }>

interface CacheEntry {
  expiresAtMs: number
  text: Promise<string | null>
}

/**
 * Caches robots.txt per origin for `ttlMs`. A 4xx answer means no robots file, so everything is allowed. A 5xx,
 * any other unexpected status, or a network error means the file is unavailable, and RFC 9309 (section 2.3.1.4)
 * then requires treating the whole origin as disallowed. That is kept for the same TTL.
 */
export class RobotsCache {
  private readonly entries = new Map<string, CacheEntry>()

  constructor(
    private readonly fetchText: RobotsFetch,
    private readonly clock: Clock,
    private readonly ttlMs: number
  ) {}

  async assertAllowed(url: string, userAgent: string): Promise<void> {
    const target = new URL(url)
    const rules = await this.rulesFor(target.origin, userAgent)
    if (!rules.isAllowed(`${target.pathname}${target.search}`)) {
      throw new WorkerError('robots_disallowed', 403, { retryable: false })
    }
  }

  private async rulesFor(origin: string, userAgent: string): Promise<RobotsRules> {
    const text = await this.textFor(origin)
    if (text === null) {
      return DISALLOW_ALL
    }
    return text === '' ? ALLOW_ALL : parseRobots(text, userAgent)
  }

  /** Resolves to the robots.txt body, `''` when there is no file, or `null` when the origin must be disallowed. */
  private textFor(origin: string): Promise<string | null> {
    const now = this.clock.now().getTime()
    const cached = this.entries.get(origin)
    if (cached !== undefined && cached.expiresAtMs > now) {
      return cached.text
    }
    const text = this.load(origin)
    this.entries.set(origin, { expiresAtMs: now + this.ttlMs, text })
    return text
  }

  private async load(origin: string): Promise<string | null> {
    try {
      const response = await this.fetchText(new URL('/robots.txt', origin).toString())
      if (response.status >= 200 && response.status < 300) {
        return response.body
      }
      if (response.status >= 400 && response.status < 500) {
        return ''
      }
      return null
    } catch {
      return null
    }
  }
}
