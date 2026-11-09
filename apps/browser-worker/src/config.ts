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
  PROXY_RESIDENTIAL_URL: z.preprocess(emptyAsUndefined, z.string().url().optional()),
  PROXY_DATACENTER_URL: z.preprocess(emptyAsUndefined, z.string().url().optional()),
  ARTIFACT_DIR: z.string().min(1).default('./artifacts'),
  ADAPTER_USER_AGENT: z
    .string()
    .min(1)
    .max(200)
    .default('APEX-EFN-bot/0.1 (+https://example.invalid/bot)'),
  ADAPTER_MIN_INTERVAL_MS: z.coerce.number().int().min(0).default(1000),
  ADAPTER_MAX_RETRIES: z.coerce.number().int().min(0).default(3),
  ADAPTER_TIMEOUT_MS: z.coerce.number().int().positive().default(15000),
  MOCK_A_BASE_URL: z.preprocess(emptyAsUndefined, z.string().url().optional()),
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
  proxyResidentialUrl: string | undefined
  proxyDatacenterUrl: string | undefined
  artifactDir: string
  adapterUserAgent: string
  adapterMinIntervalMs: number
  adapterMaxRetries: number
  adapterTimeoutMs: number
  /** Origin of the mock marketplace JSON API (`mock-a`). Unset means the adapter is not registered. */
  mockABaseUrl: string | undefined
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
    proxyResidentialUrl: values.PROXY_RESIDENTIAL_URL,
    proxyDatacenterUrl: values.PROXY_DATACENTER_URL,
    artifactDir: values.ARTIFACT_DIR,
    adapterUserAgent: values.ADAPTER_USER_AGENT,
    adapterMinIntervalMs: values.ADAPTER_MIN_INTERVAL_MS,
    adapterMaxRetries: values.ADAPTER_MAX_RETRIES,
    adapterTimeoutMs: values.ADAPTER_TIMEOUT_MS,
    mockABaseUrl: values.MOCK_A_BASE_URL,
  }
}
