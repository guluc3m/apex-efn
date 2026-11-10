import './platform/bootstrap.js'

import { randomUUID } from 'node:crypto'

import { metrics as otelMetrics } from '@opentelemetry/api'
import { Redis } from 'ioredis'

import { fetchTransport, systemSleep } from './adapters/http.js'
import { AdapterRegistry, type PlatformAdapter } from './adapters/index.js'
import { createMockAAdapter } from './adapters/mock-a/index.js'
import { FsArtifactStore } from './artifacts.js'
import { ChatService } from './chats/service.js'
import { RedisChatStore } from './chats/store.js'
import { systemClock } from './clock.js'
import { loadConfig } from './config.js'
import { buildServer } from './http/server.js'
import { RedisIdempotencyStore } from './idempotency.js'
import { BullJobService, createQueueDepthReader, startJobWorkers } from './jobs/bull.js'
import { createOtelScrapingMetrics } from './metrics.js'
import { UnleashFlags } from './platform/flags.js'
import { createLogger } from './platform/telemetry.js'

const SERVICE_NAME = 'apex-browser-worker'
const FLAG_POLL_INTERVAL_MS = 15_000

async function main(): Promise<void> {
  const logger = createLogger({
    service: SERVICE_NAME,
    level: process.env.APEX_LOG_LEVEL ?? 'info',
  })
  const config = loadConfig(process.env)
  const connection = new Redis(config.redisUrl, { maxRetriesPerRequest: null })
  const flags = UnleashFlags.fromEnv(process.env)
  const stopPolling = flags.startPolling(FLAG_POLL_INTERVAL_MS)
  const scrapingMetrics = createOtelScrapingMetrics(otelMetrics.getMeter(SERVICE_NAME))

  // Adapters are registered only when their configuration is present. The flag gate in the registry still decides
  // whether a platform is callable, so a registered adapter with its flag off is never called.
  const adapters: PlatformAdapter[] = []
  if (config.mockABaseUrl !== undefined) {
    adapters.push(
      createMockAAdapter({
        baseUrl: config.mockABaseUrl,
        transport: fetchTransport,
        clock: systemClock,
        sleep: systemSleep,
        random: Math.random,
        userAgent: config.adapterUserAgent,
        minIntervalMs: config.adapterMinIntervalMs,
        maxRetries: config.adapterMaxRetries,
        timeoutMs: config.adapterTimeoutMs,
        metrics: scrapingMetrics,
      })
    )
  }
  const registry = new AdapterRegistry(adapters, flags)
  const queueDepth = createQueueDepthReader(
    registry.status().map((status) => status.platform),
    connection
  )
  void scrapingMetrics.registerQueueDepth(() => queueDepth.read())
  const jobs = new BullJobService(registry, connection, config)
  const workers = startJobWorkers(registry, config, connection, logger, scrapingMetrics)
  const chats = new ChatService({
    registry,
    store: new RedisChatStore(connection),
    idempotency: new RedisIdempotencyStore(connection),
    artifacts: new FsArtifactStore(config.artifactDir),
    clock: systemClock,
    newId: randomUUID,
    idempotencyTtlSeconds: config.idempotencyTtlSeconds,
  })
  const app = buildServer({ token: config.token, jobs, chats, registry, logger })

  await app.listen({ host: config.host, port: config.port })
  logger.info({ host: config.host, port: config.port }, 'browser worker listening')

  const shutdown = async (signal: NodeJS.Signals): Promise<void> => {
    logger.info({ signal }, 'shutting down')
    stopPolling()
    await app.close()
    await workers.close()
    await jobs.close()
    await queueDepth.close()
    await connection.quit()
  }
  for (const signal of ['SIGINT', 'SIGTERM'] as const) {
    process.once(signal, () => {
      shutdown(signal).then(
        () => process.exit(0),
        () => process.exit(1)
      )
    })
  }
}

main().catch((error: unknown) => {
  const logger = createLogger({ service: SERVICE_NAME, level: 'fatal' })
  logger.fatal(
    { reason: error instanceof Error ? error.message : 'unknown error' },
    'browser worker failed to start'
  )
  process.exit(1)
})
