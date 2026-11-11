import { z } from 'zod'

import { phraserFromEnv } from './chat/phraser.js'
import { buildServer } from './server.js'

const Env = z.object({
  PORT: z.coerce.number().int().min(1).max(65535).default(8002),
  HOST: z.string().default('0.0.0.0'),
  MOCK_MARKETPLACE_SEED: z.coerce.number().int().nonnegative().default(0),
  /** OpenAI-compatible stub base URL. Unset: scripted seller wording only. Never a real LLM endpoint. */
  SIM_LLM_URL: z.string().url().optional(),
  /** Model name; with a real provider, e.g. `deepseek-chat`. */
  SIM_LLM_MODEL: z.string().min(1).optional(),
  /** Bearer token. `DEEPSEEK_API_KEY` is accepted as a fallback; never logged. */
  SIM_LLM_API_KEY: z.string().min(1).optional(),
  DEEPSEEK_API_KEY: z.string().min(1).optional(),
  /** Stub scenario. Ignored when an API key is present. */
  SIM_LLM_SCENARIO: z.string().min(1).optional(),
  /** Request timeout for the rephrasing call, milliseconds. */
  SIM_LLM_TIMEOUT_MS: z.coerce.number().int().positive().optional(),
})

const env = Env.parse(process.env)
const { app } = buildServer({
  seed: env.MOCK_MARKETPLACE_SEED,
  logger: true,
  phraser: phraserFromEnv(env),
})

const shutdown = () => {
  app.close().then(
    () => process.exit(0),
    () => process.exit(1)
  )
}
process.once('SIGINT', shutdown)
process.once('SIGTERM', shutdown)

await app.listen({ port: env.PORT, host: env.HOST })
