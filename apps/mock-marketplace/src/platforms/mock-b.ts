import type { FastifyInstance, FastifyReply } from 'fastify'
import { z } from 'zod'

import { findProduct, findSeller, search, sellerProducts } from '../catalog.js'
import { ChatError, type ChatEngine } from '../chat/engine.js'
import type { Catalog } from '../fixtures/schema.js'

import { chatPage, homePage, itemPage, notFoundPage, searchPage, shopPage } from './mock-b-views.js'

const P = 'mock-b'

function html(reply: FastifyReply, body: string, status = 200) {
  return reply.code(status).type('text/html; charset=utf-8').send(body)
}

const OpenChat = z.object({ seller: z.string(), item: z.string() })
const SendMessage = z.object({ text: z.string() })

export function registerMockB(app: FastifyInstance, catalog: Catalog, chats: ChatEngine): void {
  const sellers = new Map(catalog.sellers.map((s) => [s.id, s]))

  app.get('/mock-b/', async (_req, reply) => html(reply, homePage()))

  app.get<{ Querystring: { q?: string } }>('/mock-b/search', async (req, reply) => {
    const q = typeof req.query.q === 'string' ? req.query.q : ''
    return html(reply, searchPage(q, search(catalog, P, q), sellers))
  })

  app.get<{ Params: { id: string } }>('/mock-b/item/:id', async (req, reply) => {
    const p = findProduct(catalog, P, req.params.id)
    const s = p ? sellers.get(p.sellerId) : undefined
    if (!p || !s) return html(reply, notFoundPage('Item'), 404)
    return html(reply, itemPage(p, s))
  })

  app.get<{ Params: { id: string } }>('/mock-b/shop/:id', async (req, reply) => {
    const s = findSeller(catalog, P, req.params.id)
    if (!s) return html(reply, notFoundPage('Shop'), 404)
    return html(reply, shopPage(s, sellerProducts(catalog, s.id)))
  })

  app.post('/mock-b/chat', async (req, reply) => {
    const parsed = OpenChat.safeParse(req.body)
    if (!parsed.success) return html(reply, notFoundPage('Chat'), 400)
    try {
      const chat = chats.open(P, parsed.data.seller, parsed.data.item)
      return reply.redirect(`/mock-b/chat/${chat.id}`, 303)
    } catch (e) {
      if (e instanceof ChatError) return html(reply, notFoundPage('Seller or item'), 404)
      throw e
    }
  })

  app.get<{ Params: { id: string } }>('/mock-b/chat/:id', async (req, reply) => {
    try {
      const chat = chats.snapshot(req.params.id)
      if (chat.platform !== P) return html(reply, notFoundPage('Chat'), 404)
      const seller = sellers.get(chat.sellerId)
      const product = findProduct(catalog, P, chat.productId)
      return html(
        reply,
        chatPage(chat, seller?.name ?? chat.sellerId, product?.title ?? chat.productId)
      )
    } catch (e) {
      if (e instanceof ChatError) return html(reply, notFoundPage('Chat'), 404)
      throw e
    }
  })

  app.post<{ Params: { id: string } }>('/mock-b/chat/:id/send', async (req, reply) => {
    const parsed = SendMessage.safeParse(req.body)
    if (!parsed.success) return html(reply, notFoundPage('Message'), 400)
    try {
      if (chats.get(req.params.id).platform !== P) return html(reply, notFoundPage('Chat'), 404)
      chats.send(req.params.id, parsed.data.text)
      return reply.redirect(`/mock-b/chat/${req.params.id}`, 303)
    } catch (e) {
      if (e instanceof ChatError) {
        return html(
          reply,
          notFoundPage(e.code === 'empty_message' ? 'Message' : 'Chat'),
          e.code === 'empty_message' ? 400 : 404
        )
      }
      throw e
    }
  })
}
