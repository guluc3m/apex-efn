/**
 * Response shapes of the mock-a JSON API (apps/mock-marketplace/src/platforms/mock-a.ts). These describe the platform's
 * own vocabulary, not our contract, so they are written by hand. Money is a decimal string, dates are epoch seconds and
 * percentages are on a 0 to 100 scale. Only fields the adapter reads are listed.
 */
import { z } from 'zod'

const epochSeconds = z.number().int().nonnegative()
const count = z.number().int().nonnegative()
const percent = z.number().min(0).max(100)

const Price = z.object({
  amount: z.string().nullable(),
  currency: z.string().nullable(),
})

export const ListingSchema = z.object({
  listing_id: z.string().min(1),
  name: z.string(),
  url: z.string().min(1),
  price: Price.nullable(),
  min_order_qty: z.number().int().positive(),
  vendor: z.object({
    vendor_id: z.string().min(1),
    display_name: z.string().nullable(),
  }),
})
export type MockListing = z.infer<typeof ListingSchema>

export const SearchPageSchema = z.object({
  query: z.string(),
  total: count,
  page: z.number().int().positive(),
  results: z.array(ListingSchema),
})
export type MockSearchPage = z.infer<typeof SearchPageSchema>

export const ProductSchema = ListingSchema.extend({
  attributes: z.array(z.object({ key: z.string(), value: z.string() })),
  certs: z.array(z.string()),
  bulk_pricing: z.array(
    z.object({
      from_qty: z.number().int().positive(),
      to_qty: z.number().int().positive().nullable(),
      price: z.string(),
    })
  ),
  delivery: z
    .object({
      fee: z.string(),
      currency: z.string(),
      eta_days: z.tuple([count, count]),
    })
    .nullable(),
  trade_term: z.string().nullable(),
  production_days: count.nullable(),
})
export type MockProduct = z.infer<typeof ProductSchema>

export const SellerSchema = z.object({
  vendor_id: z.string().min(1),
  display_name: z.string(),
  location: z.string().nullable(),
  listings: z.array(z.string()),
})
export type MockSeller = z.infer<typeof SellerSchema>

export const MetricsSchema = z.object({
  vendor_id: z.string().min(1),
  registered_at: epochSeconds.nullable(),
  first_order_at: epochSeconds.nullable(),
  active_months_12: z.number().int().min(0).max(12).nullable(),
  orders: z.object({ lifetime: count.nullable(), last_12m: count.nullable() }),
  turnover_12m: z.object({ amount: z.string(), currency: z.string().nullable() }).nullable(),
  repeat_customers_pct: percent.nullable(),
  catalog: z.object({
    listings: count.nullable(),
    churn_30d_pct: percent.nullable(),
    completeness_pct: percent.nullable(),
  }),
  feedback: z.object({
    count: count.nullable(),
    count_12m: count.nullable(),
    score_0_100: percent.nullable(),
    rated_orders: count.nullable(),
    verified_pct: percent.nullable(),
  }),
  reply_rate_pct: percent.nullable(),
  badges: z.object({
    kyc: z.boolean().nullable(),
    buyer_protection: z.boolean().nullable(),
    escrow: z.boolean().nullable(),
  }),
  disputes_pct: percent.nullable(),
  refunds_pct: percent.nullable(),
})
export type MockMetrics = z.infer<typeof MetricsSchema>

export const ReviewsSchema = z.object({
  vendor_id: z.string().min(1),
  reviews: z.array(
    z.object({
      review_id: z.string().min(1),
      stars: z.number().int().min(1).max(5),
      comment: z.string().nullable(),
      posted_at: epochSeconds.nullable(),
      verified_order: z.boolean(),
    })
  ),
})
export type MockReviews = z.infer<typeof ReviewsSchema>

export const ConversationSchema = z.object({ conversation_id: z.string().min(1) })

const MessageSchema = z.object({
  id: z.number().int().positive(),
  from: z.enum(['buyer', 'vendor']),
  body: z.string(),
  sent_at: epochSeconds,
})
export type MockMessage = z.infer<typeof MessageSchema>

export const SentMessageSchema = z.object({ message: MessageSchema })

export const MessagesSchema = z.object({
  conversation_id: z.string().min(1),
  messages: z.array(MessageSchema),
})
export type MockMessages = z.infer<typeof MessagesSchema>

/** Error body the mock returns with 4xx answers, e.g. `{"error":"vendor_not_found"}`. */
export const ErrorBodySchema = z.object({ error: z.string() })
