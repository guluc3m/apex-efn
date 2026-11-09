import {
  zAcquireChatLockRequest,
  zOpenChatRequest,
  zProductJobRequest,
  zReleaseChatLockQuery,
  zSearchJobRequest,
  zSellerJobRequest,
  zSellerSignalsJobRequest,
  zSendChatMessageRequest,
} from '@apex/shared-types/contracts/browser-worker/zod'
import { z } from 'zod'

// The generated objects strip unknown keys. The contract sets additionalProperties: false, so the request
// bodies are strict here. Schemas come from the generated contract; only the strictness is added.
export const jobRequestSchema = z.discriminatedUnion('kind', [
  zSearchJobRequest.extend({ kind: z.literal('search') }).strict(),
  zProductJobRequest.extend({ kind: z.literal('product') }).strict(),
  zSellerJobRequest.extend({ kind: z.literal('seller') }).strict(),
  zSellerSignalsJobRequest.extend({ kind: z.literal('seller_signals') }).strict(),
])

export const openChatBodySchema = zOpenChatRequest.strict()

export const sendChatMessageBodySchema = zSendChatMessageRequest.strict()

export const acquireChatLockBodySchema = zAcquireChatLockRequest.strict()

export const releaseChatLockQuerySchema = zReleaseChatLockQuery

// Query values arrive as strings, so these numbers are coerced. Bounds match the contract.
export const readChatMessagesQuerySchema = z.object({
  after_seq: z.coerce.number().int().min(0).default(0),
  limit: z.coerce.number().int().min(1).max(200).default(100),
})
