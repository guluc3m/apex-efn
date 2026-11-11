import { z } from 'zod'

const emptyAsUndefined = (value: unknown): unknown => (value === '' ? undefined : value)

const envSchema = z.object({
  REDIS_URL: z.string().url().default('redis://localhost:6379'),
  HOST: z.string().min(1).default('0.0.0.0'),
  PORT: z.coerce.number().int().min(1).max(65535).default(4010),
  BROWSER_WORKER_TOKEN: z.string().min(32),
  SCRAPING_CONCURRENCY: z.coerce.number().int().positive().default(3),
  JOB_ATTEMPTS: z.coerce.number().int().positive().default(3),
  JOB_BACKOFF_MS: z.coerce.number().int().positive().default(2000),
  IDEMPOTENCY_TTL_SECONDS: z.coerce.number().int().positive().default(86400),
  BROWSER_POOL_SIZE: z.coerce.number().int().positive().default(5),
  MAX_PAGES_PER_BROWSER: z.coerce.number().int().positive().default(50),
  BROWSER_MAX_MEMORY_MB: z.coerce.number().int().min(0).default(1024),
  BROWSER_ACQUIRE_TIMEOUT_MS: z.coerce.number().int().positive().default(30_000),
  BROWSER_IDLE_TIMEOUT_MS: z.coerce.number().int().positive().default(300_000),
  BROWSER_SWEEP_INTERVAL_MS: z.coerce.number().int().positive().default(30_000),
  PROXY_RESIDENTIAL_URL: z.preprocess(emptyAsUndefined, z.string().url().optional()),
  PROXY_DATACENTER_URL: z.preprocess(emptyAsUndefined, z.string().url().optional()),
  ARTIFACT_DIR: z.string().min(1).default('./artifacts'),
  // The User-Agent goes to every platform in clear text and lands in their logs. It identifies the product, never
  // a person, a tenant or a credential: an email or an identity word here is a leak to a third party (see
  // docs/compliance/wallapop.md section 6). The default is a product token plus an organisational URL.
  ADAPTER_USER_AGENT: z
    .string()
    .min(1)
    .max(200)
    .refine(
      (value) =>
        !value.includes('@') &&
        !/\b(token|secret|tenant|account|password|apikey|api[_-]?key)/i.test(value),
      {
        message:
          'must be an anonymous product token; emails, credentials, tenant or account identifiers are forbidden',
      }
    )
    .default('APEX-EFN-bot/0.1 (+https://example.invalid/bot)'),
  ADAPTER_MIN_INTERVAL_MS: z.coerce.number().int().min(0).default(1000),
  ADAPTER_MAX_RETRIES: z.coerce.number().int().min(0).default(3),
  ADAPTER_TIMEOUT_MS: z.coerce.number().int().positive().default(15000),
  MOCK_A_BASE_URL: z.preprocess(emptyAsUndefined, z.string().url().optional()),
  MOCK_B_BASE_URL: z.preprocess(emptyAsUndefined, z.string().url().optional()),
})

export interface WorkerConfig {
  redisUrl: string
  host: string
  port: number
  token: string
  scrapingConcurrency: number
  jobAttempts: number
  jobBackoffMs: number
  idempotencyTtlSeconds: number
  browserPoolSize: number
  maxPagesPerBrowser: number
  /** Resident memory above which a browser is recycled. `0` disables the check. */
  browserMaxMemoryMb: number
  /** How long a job waits for a free browser before it answers `timeout`. */
  browserAcquireTimeoutMs: number
  /** How long a browser with no open pages stays alive. */
  browserIdleTimeoutMs: number
  /** How often the pool watchdog applies the recycling rules. */
  browserSweepIntervalMs: number
  proxyResidentialUrl: string | undefined
  proxyDatacenterUrl: string | undefined
  artifactDir: string
  adapterUserAgent: string
  adapterMinIntervalMs: number
  adapterMaxRetries: number
  adapterTimeoutMs: number
  /** Origin of the mock marketplace JSON API (`mock-a`). Unset means the adapter is not registered. */
  mockABaseUrl: string | undefined
  /** Origin of the mock marketplace HTML site (`mock-b`). Unset means the adapter is not registered. */
  mockBBaseUrl: string | undefined
}

/** Throws with the names of the invalid keys only. Values (the token, proxy credentials) never appear in the message. */
export function loadConfig(env: NodeJS.ProcessEnv): WorkerConfig {
  const result = envSchema.safeParse(env)
  if (!result.success) {
    const keys = [...new Set(result.error.issues.map((issue) => String(issue.path[0] ?? 'env')))]
    throw new Error(`invalid browser worker configuration: ${keys.join(', ')}`)
  }
  const values = result.data
  return {
    redisUrl: values.REDIS_URL,
    host: values.HOST,
    port: values.PORT,
    token: values.BROWSER_WORKER_TOKEN,
    scrapingConcurrency: values.SCRAPING_CONCURRENCY,
    jobAttempts: values.JOB_ATTEMPTS,
    jobBackoffMs: values.JOB_BACKOFF_MS,
    idempotencyTtlSeconds: values.IDEMPOTENCY_TTL_SECONDS,
    browserPoolSize: values.BROWSER_POOL_SIZE,
    maxPagesPerBrowser: values.MAX_PAGES_PER_BROWSER,
    browserMaxMemoryMb: values.BROWSER_MAX_MEMORY_MB,
    browserAcquireTimeoutMs: values.BROWSER_ACQUIRE_TIMEOUT_MS,
    browserIdleTimeoutMs: values.BROWSER_IDLE_TIMEOUT_MS,
    browserSweepIntervalMs: values.BROWSER_SWEEP_INTERVAL_MS,
    proxyResidentialUrl: values.PROXY_RESIDENTIAL_URL,
    proxyDatacenterUrl: values.PROXY_DATACENTER_URL,
    artifactDir: values.ARTIFACT_DIR,
    adapterUserAgent: values.ADAPTER_USER_AGENT,
    adapterMinIntervalMs: values.ADAPTER_MIN_INTERVAL_MS,
    adapterMaxRetries: values.ADAPTER_MAX_RETRIES,
    adapterTimeoutMs: values.ADAPTER_TIMEOUT_MS,
    mockABaseUrl: values.MOCK_A_BASE_URL,
    mockBBaseUrl: values.MOCK_B_BASE_URL,
  }
}
