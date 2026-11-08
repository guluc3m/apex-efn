import type { FastifyInstance } from 'fastify'
import { z } from 'zod'

import { ChatError, type ChatEngine } from './chat/engine.js'
import { PersonaIdSchema } from './fixtures/schema.js'

/**
 * Test-only control surface. A real platform never has this: adapters must not call it, only tests and
 * the adversarial suite (D5-09) do, to reset state, pick personas and read the seller's ground truth.
 */

const Reset = z.object({ seed: z.number().int().nonnegative().optional() }).strict()
const SetPersona = z.object({ persona: PersonaIdSchema }).strict()

export function registerControl(app: FastifyInstance, chats: ChatEngine): void {
  app.post('/__control/reset', async (req, reply) => {
    const parsed = Reset.safeParse(req.body ?? {})
    if (!parsed.success)
      return reply.code(400).send({ error: 'bad_request', issues: parsed.error.issues })
    chats.reset(parsed.data.seed)
    return { ok: true, seed: chats.currentSeed }
  })

  app.put<{ Params: { sellerId: string } }>(
    '/__control/sellers/:sellerId/persona',
    async (req, reply) => {
      const parsed = SetPersona.safeParse(req.body)
      if (!parsed.success)
        return reply.code(400).send({ error: 'bad_request', issues: parsed.error.issues })
      try {
        chats.setPersona(req.params.sellerId, parsed.data.persona)
        return { sellerId: req.params.sellerId, persona: parsed.data.persona }
      } catch (e) {
        if (e instanceof ChatError) return reply.code(404).send({ error: e.code })
        throw e
      }
    }
  )

  app.put<{ Params: { chatId: string } }>(
    '/__control/chats/:chatId/persona',
    async (req, reply) => {
      const parsed = SetPersona.safeParse(req.body)
      if (!parsed.success)
        return reply.code(400).send({ error: 'bad_request', issues: parsed.error.issues })
      try {
        chats.setChatPersona(req.params.chatId, parsed.data.persona)
        return { chatId: req.params.chatId, persona: parsed.data.persona }
      } catch (e) {
        if (e instanceof ChatError) return reply.code(404).send({ error: e.code })
        throw e
      }
    }
  )

  app.get('/__control/chats', () => ({ chats: chats.list() }))

  app.get<{ Params: { chatId: string } }>('/__control/chats/:chatId', async (req, reply) => {
    try {
      return chats.snapshot(req.params.chatId)
    } catch (e) {
      if (e instanceof ChatError) return reply.code(404).send({ error: e.code })
      throw e
    }
  })
}
