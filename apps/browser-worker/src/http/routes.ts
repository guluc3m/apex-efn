import type { FastifyInstance } from 'fastify'

import type { ChatService } from '../chats/service.js'
import { WorkerError } from '../errors.js'
import type { JobService } from '../jobs/service.js'

import {
  acquireChatLockBodySchema,
  jobRequestSchema,
  openChatBodySchema,
  readChatMessagesQuerySchema,
  releaseChatLockQuerySchema,
  sendChatMessageBodySchema,
} from './schemas.js'
import { parseWith, requireIdempotencyKey } from './validation.js'

interface ChatParams {
  chat_id: string
}

export function registerJobRoutes(app: FastifyInstance, jobs: JobService): void {
  app.post<{ Body: unknown }>('/internal/v1/jobs', async (request, reply) => {
    const key = requireIdempotencyKey(request.headers['idempotency-key'])
    const body = parseWith(jobRequestSchema, request.body)
    const accepted = await jobs.enqueue(body, key)
    return reply.code(202).send(accepted)
  })

  app.get<{ Params: { id: string } }>('/internal/v1/jobs/:id', async (request) => {
    const state = await jobs.get(request.params.id)
    if (state === null) {
      throw new WorkerError('unknown_job', 404)
    }
    return state
  })
}

export function registerChatRoutes(app: FastifyInstance, chats: ChatService): void {
  app.post<{ Body: unknown }>('/internal/v1/chats', async (request, reply) => {
    const key = requireIdempotencyKey(request.headers['idempotency-key'])
    const body = parseWith(openChatBodySchema, request.body)
    const response = await chats.open(body, key)
    return reply.code(response.status).send(response.body)
  })

  app.get<{ Params: ChatParams }>('/internal/v1/chats/:chat_id', async (request) => {
    return chats.get(request.params.chat_id)
  })

  app.get<{ Params: ChatParams; Querystring: unknown }>(
    '/internal/v1/chats/:chat_id/messages',
    async (request) => {
      const query = parseWith(readChatMessagesQuerySchema, request.query)
      return chats.read(request.params.chat_id, query.after_seq, query.limit)
    }
  )

  app.post<{ Params: ChatParams; Body: unknown }>(
    '/internal/v1/chats/:chat_id/messages',
    async (request, reply) => {
      const key = requireIdempotencyKey(request.headers['idempotency-key'])
      const body = parseWith(sendChatMessageBodySchema, request.body)
      const response = await chats.send(request.params.chat_id, body, key)
      return reply.code(response.status).send(response.body)
    }
  )

  app.post<{ Params: ChatParams }>(
    '/internal/v1/chats/:chat_id/screenshots',
    async (request, reply) => {
      const key = requireIdempotencyKey(request.headers['idempotency-key'])
      const response = await chats.screenshot(request.params.chat_id, key)
      return reply.code(response.status).send(response.body)
    }
  )

  app.put<{ Params: ChatParams; Body: unknown }>(
    '/internal/v1/chats/:chat_id/lock',
    async (request) => {
      const body = parseWith(acquireChatLockBodySchema, request.body)
      return chats.acquireLock(request.params.chat_id, body)
    }
  )

  app.delete<{ Params: ChatParams; Querystring: unknown }>(
    '/internal/v1/chats/:chat_id/lock',
    async (request, reply) => {
      const query = parseWith(releaseChatLockQuerySchema, request.query)
      await chats.releaseLock(request.params.chat_id, query.user_id)
      return reply.code(204).send()
    }
  )
}
