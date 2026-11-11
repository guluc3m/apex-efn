import Fastify, { type FastifyInstance } from 'fastify'

import { ChatEngine } from './chat/engine.js'
import type { ChatPhraser } from './chat/phraser.js'
import { systemClock, type Clock } from './clock.js'
import { registerControl } from './control.js'
import { loadCatalog } from './fixtures/load.js'
import { PERSONA_IDS, PLATFORM_IDS, type Catalog } from './fixtures/schema.js'
import { registerMockA } from './platforms/mock-a.js'
import { registerMockB } from './platforms/mock-b.js'
import { registerMockC } from './platforms/mock-c.js'

export interface BuildOptions {
  catalog?: Catalog
  clock?: Clock
  seed?: number
  logger?: boolean
  /** Optional wording-only rephraser; tests inject a fake, `index.ts` builds the stub client. */
  phraser?: ChatPhraser
}

export interface MockMarketplace {
  app: FastifyInstance
  chats: ChatEngine
  catalog: Catalog
}

const ROBOTS = `User-agent: *
Disallow: /__control/
Allow: /
`

export function buildServer(options: BuildOptions = {}): MockMarketplace {
  const catalog = options.catalog ?? loadCatalog()
  const chats = new ChatEngine(
    catalog,
    options.clock ?? systemClock,
    options.seed ?? 0,
    options.phraser
  )
  const app = Fastify({ logger: options.logger ?? false })

  // HTML forms on mock-b post urlencoded bodies; no extra plugin needed for flat fields.
  app.addContentTypeParser(
    'application/x-www-form-urlencoded',
    { parseAs: 'string' },
    (_req, body, done) => {
      done(null, Object.fromEntries(new URLSearchParams(String(body))))
    }
  )

  app.get('/healthz', () => ({
    status: 'ok',
    platforms: PLATFORM_IDS,
    personas: PERSONA_IDS,
    sellers: catalog.sellers.length,
    products: catalog.products.length,
  }))
  app.get('/robots.txt', async (_req, reply) => reply.type('text/plain').send(ROBOTS))

  registerMockA(app, catalog, chats)
  registerMockB(app, catalog, chats)
  registerMockC(app, catalog, chats)
  registerControl(app, chats)

  return { app, chats, catalog }
}
