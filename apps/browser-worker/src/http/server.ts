import Fastify, { type FastifyBaseLogger, type FastifyInstance } from 'fastify'

import type { AdapterRegistry } from '../adapters/index.js'
import type { ChatService } from '../chats/service.js'
import { toProblem, WorkerError } from '../errors.js'
import type { JobService } from '../jobs/service.js'

import { isServiceTokenValid } from './auth.js'
import { problemFor, sendProblem } from './problems.js'
import { registerChatRoutes, registerJobRoutes } from './routes.js'

export const HEALTH_PATH = '/internal/v1/health'

export interface WorkerServerDeps {
  token: string
  jobs: JobService
  chats: ChatService
  registry: AdapterRegistry
  /** The redacting telemetry logger. Without one, the server does not log. */
  logger?: FastifyBaseLogger
}

export function buildServer(deps: WorkerServerDeps): FastifyInstance {
  const app: FastifyInstance =
    deps.logger === undefined
      ? Fastify({ logger: false })
      : Fastify({ loggerInstance: deps.logger })

  app.addHook('onRequest', (request, _reply, done) => {
    if (
      request.routeOptions.url === HEALTH_PATH ||
      isServiceTokenValid(request.headers.authorization, deps.token)
    ) {
      done()
      return
    }
    done(new WorkerError('unauthorized', 401))
  })

  app.setErrorHandler((error, request, reply) => {
    const problem = problemFor(error, instancePath(request.url))
    if (problem.status >= 500) {
      request.log.error(
        { errorName: error instanceof Error ? error.name : 'unknown' },
        'request failed'
      )
    }
    return sendProblem(reply, problem)
  })

  app.setNotFoundHandler((request, reply) => {
    const problem = toProblem(
      new WorkerError('validation_error', 404, { detail: 'route not found' })
    )
    return sendProblem(reply, { ...problem, instance: instancePath(request.url) })
  })

  app.get(HEALTH_PATH, () => ({ status: 'ok', platforms: deps.registry.status() }))
  registerJobRoutes(app, deps.jobs)
  registerChatRoutes(app, deps.chats)

  return app
}

function instancePath(url: string): string {
  return url.split('?')[0] ?? url
}
