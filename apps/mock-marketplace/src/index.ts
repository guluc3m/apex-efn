import { z } from 'zod'

import { createPhraser } from './chat/phraser.js'
import { buildServer } from './server.js'

const Env = z.object({
  PORT: z.coerce.number().int().min(1).max(65535).default(8002),
  HOST: z.string().default('0.0.0.0'),
  MOCK_MARKETPLACE_SEED: z.coerce.number().int().nonnegative().default(0),
  /** OpenAI-compatible stub base URL. Unset: scripted seller wording only. Never a real LLM endpoint. */
  SIM_LLM_URL: z.string().url().optional(),
})

const env = Env.parse(process.env)
const { app } = buildServer({
  seed: env.MOCK_MARKETPLACE_SEED,
  logger: true,
  phraser: createPhraser(env.SIM_LLM_URL),
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
