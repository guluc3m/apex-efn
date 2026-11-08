/**
 * Feature flags over the Unleash client API. Fail closed: unknown, unreachable or unsupported means off.
 * Naming convention and defaults: docs/observability/flags.md. Mirrors apps/orchestrator/src/apex/platform/flags.py.
 */
import { z } from 'zod'

export const DEFAULT_APP_NAME = 'apex-browser-worker'

const SEGMENT = '[a-z0-9_-]+'
const FLAG_PATTERNS: readonly RegExp[] = [
  new RegExp(`^platform\\.${SEGMENT}\\.enabled$`),
  new RegExp(`^negotiation\\.strategy\\.${SEGMENT}$`),
  /^negotiation\.autonomous_send$/,
  new RegExp(`^sanity\\.bands\\.${SEGMENT}$`),
  new RegExp(`^trust\\.model\\.${SEGMENT}$`),
]
const ROLLOUT_RE = /^\d{1,3}$/

export function validateFlagName(name: string): string {
  if (!FLAG_PATTERNS.some((pattern) => pattern.test(name))) {
    throw new Error(`malformed feature flag name "${name}"; see docs/observability/flags.md`)
  }
  return name
}

export function platformFlagName(platformId: string): string {
  return validateFlagName(`platform.${platformId}.enabled`)
}

export type FlagContext = Readonly<Record<string, string>>

export interface FlagProvider {
  isEnabled(name: string, context?: FlagContext): boolean
  isPlatformEnabled(platformId: string): boolean
}

export class StaticFlags implements FlagProvider {
  private readonly flags: ReadonlyMap<string, boolean>

  constructor(flags: Readonly<Record<string, boolean>> = {}) {
    this.flags = new Map(
      Object.entries(flags).map(([name, value]) => [validateFlagName(name), value] as const)
    )
  }

  isEnabled(name: string, _context?: FlagContext): boolean {
    validateFlagName(name)
    return this.flags.get(name) ?? false
  }

  isPlatformEnabled(platformId: string): boolean {
    return this.isEnabled(platformFlagName(platformId))
  }
}

const strategySchema = z.object({
  name: z.string(),
  parameters: z.record(z.unknown()).optional(),
  constraints: z.array(z.unknown()).optional(),
  segments: z.array(z.unknown()).optional(),
  disabled: z.boolean().optional(),
})

const featureSchema = z.object({
  name: z.string(),
  enabled: z.boolean(),
  strategies: z.array(strategySchema).optional(),
})

const featuresPayloadSchema = z.object({
  features: z.array(featureSchema),
})

type Feature = z.infer<typeof featureSchema>
type Strategy = z.infer<typeof strategySchema>

export interface UnleashFlagsOptions {
  baseUrl: string
  clientToken: string
  appName?: string
  instanceId?: string
  timeoutMs?: number
  fetchImpl?: typeof fetch
  now?: () => Date
}

export class UnleashFlags implements FlagProvider {
  private readonly url: string
  private readonly headers: Record<string, string>
  private readonly timeoutMs: number
  private readonly fetchImpl: typeof fetch
  private readonly now: () => Date
  private snapshot = new Map<string, Feature>()
  private lastRefreshedAt: Date | null = null
  private readonly warned = new Set<string>()

  constructor(options: UnleashFlagsOptions) {
    this.url = `${options.baseUrl.replace(/\/+$/, '')}/client/features`
    this.headers = {
      Authorization: options.clientToken,
      'UNLEASH-APPNAME': options.appName ?? DEFAULT_APP_NAME,
      'UNLEASH-INSTANCEID': options.instanceId ?? DEFAULT_APP_NAME,
      Accept: 'application/json',
    }
    this.timeoutMs = options.timeoutMs ?? 5000
    this.fetchImpl = options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init))
    this.now = options.now ?? (() => new Date())
  }

  static fromEnv(
    env: Readonly<Record<string, string | undefined>> = process.env,
    appName: string = DEFAULT_APP_NAME
  ): UnleashFlags {
    const url = env.UNLEASH_URL
    const token = env.UNLEASH_API_TOKEN
    if (!url || !token) {
      throw new Error('UNLEASH_URL and UNLEASH_API_TOKEN must be set')
    }
    return new UnleashFlags({ baseUrl: url, clientToken: token, appName })
  }

  get lastRefreshed(): Date | null {
    return this.lastRefreshedAt
  }

  async refresh(): Promise<boolean> {
    try {
      const response = await this.fetchImpl(this.url, {
        headers: this.headers,
        signal: AbortSignal.timeout(this.timeoutMs),
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const payload = featuresPayloadSchema.parse(await response.json())
      this.snapshot = new Map(payload.features.map((feature) => [feature.name, feature]))
      this.lastRefreshedAt = this.now()
      return true
    } catch (err) {
      const reason = err instanceof Error ? `${err.name}: ${err.message}` : 'unknown error'
      console.warn(
        `feature flag refresh failed (${reason}); keeping last snapshot of ${this.snapshot.size} flags`
      )
      return false
    }
  }

  /** Refreshes every `intervalMs` until the returned function is called. */
  startPolling(intervalMs: number): () => void {
    void this.refresh()
    const timer = setInterval(() => void this.refresh(), intervalMs)
    return () => clearInterval(timer)
  }

  isEnabled(name: string, _context?: FlagContext): boolean {
    validateFlagName(name)
    const feature = this.snapshot.get(name)
    if (!feature?.enabled) {
      return false
    }
    const strategies = feature.strategies ?? []
    if (strategies.length === 0) {
      return true
    }
    return strategies.some((strategy) => this.evaluate(strategy, name))
  }

  isPlatformEnabled(platformId: string): boolean {
    return this.isEnabled(platformFlagName(platformId))
  }

  private evaluate(strategy: Strategy, flag: string): boolean {
    if (strategy.disabled) {
      return false
    }
    if ((strategy.constraints?.length ?? 0) > 0 || (strategy.segments?.length ?? 0) > 0) {
      this.warnOnce(`${flag}|${strategy.name}|constraints`, 'constraints/segments unsupported')
      return false
    }
    if (strategy.name === 'default') {
      return true
    }
    if (strategy.name === 'flexibleRollout') {
      return this.rollout(strategy.parameters?.rollout, flag)
    }
    this.warnOnce(`${flag}|${strategy.name}`, `strategy "${strategy.name}" unsupported`)
    return false
  }

  private rollout(rollout: unknown, flag: string): boolean {
    const text = String(rollout)
    if (!ROLLOUT_RE.test(text)) {
      this.warnOnce(`${flag}|rollout`, `rollout value "${text}" unsupported`)
      return false
    }
    const percent = Number(text)
    if (percent === 100) {
      return true
    }
    if (percent === 0) {
      return false
    }
    this.warnOnce(`${flag}|rollout`, `partial rollout ${percent}% unsupported, treated as off`)
    return false
  }

  private warnOnce(key: string, message: string): void {
    if (this.warned.has(key)) {
      return
    }
    this.warned.add(key)
    console.warn(`feature flag: ${message} (fail closed)`)
  }
}
