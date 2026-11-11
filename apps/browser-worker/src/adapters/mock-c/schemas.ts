/**
 * Wire schemas for the `mock-c` API.
 *
 * mock-c is deliberately its own dialect: integer cents instead of decimal strings, basis points instead of
 * percentages, ISO dates, and a threads/messages resource for the negotiation. The adapter's job is to turn that
 * into the contract's raw shapes; these schemas fail loudly when the platform changes.
 */

import { z } from 'zod'

const money = z.object({ cents: z.number().int().nonnegative(), currency: z.string().min(3).max(3) })
const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)

export const SummarySchema = z.object({
  item_id: z.string().min(1),
  title: z.string().min(1),
  unit_price: money,
  min_order: z.number().int().positive(),
  supplier_id: z.string().min(1),
  supplier_name: z.string().nullable(),
  url: z.string().optional(),
})

export const SearchSchema = z.object({
  query: z.string(),
  count: z.number().int().nonnegative(),
  items: z.array(SummarySchema),
})

export const ItemSchema = SummarySchema.extend({
  description: z.string(),
  supplier: z.object({
    supplier_id: z.string(),
    name: z.string().nullable(),
    country: z.string().nullable(),
  }),
  tiers: z.array(
    z.object({
      from: z.number().int().positive(),
      to: z.number().int().positive().nullable(),
      unit_price: money,
    })
  ),
  specs: z.array(z.object({ name: z.string(), value: z.string() })),
  certifications: z.array(z.string()),
  shipping: z
    .object({
      cost: money,
      min_days: z.number().int().nonnegative(),
      max_days: z.number().int().nonnegative(),
    })
    .nullable(),
  incoterm: z.string().nullable(),
  lead_time_days: z.number().int().nonnegative().nullable(),
})

export const SupplierSchema = z.object({
  supplier_id: z.string().min(1),
  name: z.string().min(1),
  country: z.string().length(2).nullable(),
  member_since: isoDate.nullable(),
  profile_url: z.string().optional(),
})

const nullableInt = z.number().int().nullable()

export const MetricsSchema = z.object({
  supplier_id: z.string().min(1),
  member_since: isoDate.nullable(),
  first_order_at: isoDate.nullable(),
  months_active_12: nullableInt,
  orders: z.object({ total: nullableInt, last_12m: nullableInt }),
  revenue_12m: money.nullable(),
  repeat_rate_bp: nullableInt,
  catalog: z.object({
    listings: nullableInt,
    churn_30d_bp: nullableInt,
    completeness_bp: nullableInt,
  }),
  reviews: z.object({
    total: nullableInt,
    last_12m: nullableInt,
    avg: z.number().nullable(),
    count: nullableInt,
    verified_bp: nullableInt,
  }),
  response_rate_bp: nullableInt,
  identity_verified: z.boolean().nullable(),
  trade_assurance: z.boolean().nullable(),
  escrow: z.boolean().nullable(),
  dispute_bp: nullableInt,
  refund_bp: nullableInt,
  recent_reviews: z.array(
    z.object({
      rating: z.number().int().min(1).max(5),
      date: isoDate,
      verified: z.boolean(),
      text: z.string(),
    })
  ),
})

export const ThreadOpenedSchema = z.object({
  thread_id: z.string().min(1),
  supplier_id: z.string().min(1),
  item_id: z.string().min(1),
})

export const WireMessageSchema = z.object({
  seq: z.number().int().positive(),
  author: z.enum(['buyer', 'supplier']),
  body: z.string(),
  sent_at: z.number().int().nonnegative(),
})

export const SendResultSchema = z.object({
  sent: WireMessageSchema.nullable(),
  received: z.array(WireMessageSchema),
})

export const MessagesSchema = z.object({
  thread_id: z.string().min(1),
  messages: z.array(WireMessageSchema),
})

export const ApiErrorSchema = z.object({
  error: z.object({ code: z.string(), message: z.string().optional() }),
})

export type Summary = z.infer<typeof SummarySchema>
export type SearchPage = z.infer<typeof SearchSchema>
export type Item = z.infer<typeof ItemSchema>
export type Supplier = z.infer<typeof SupplierSchema>
export type Metrics = z.infer<typeof MetricsSchema>
export type ThreadOpened = z.infer<typeof ThreadOpenedSchema>
export type SendResult = z.infer<typeof SendResultSchema>
export type MessagesPage = z.infer<typeof MessagesSchema>
export type WireMessage = z.infer<typeof WireMessageSchema>
