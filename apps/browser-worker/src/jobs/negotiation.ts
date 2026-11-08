/**
 * Negotiation job processor
 */

import type { Job } from 'bullmq'

export interface NegotiationJobData {
  offerId: string
  platform: string
  sellerId: string
  strategy: {
    targetDiscount: number
    maxDiscount: number
    maxRounds: number
    tone: 'formal' | 'casual'
    allowCounterpartites: boolean
  }
}

export interface NegotiationJobResult {
  initialPrice: number
  finalPrice: number
  discountPct: number
  rounds: number
  messages: Array<{
    role: 'agent' | 'seller'
    content: string
    timestamp: string
  }>
  outcome: 'success' | 'no_response' | 'rejected' | 'escalated'
}

// eslint-disable-next-line @typescript-eslint/require-await -- stub hasta implementar el job
export async function processNegotiationJob(
  job: Job<NegotiationJobData>
): Promise<NegotiationJobResult> {
  const { offerId, platform, sellerId } = job.data

  console.log(`Processing negotiation job for offer ${offerId} on ${platform} with seller ${sellerId}`)

  // TODO: Implement actual negotiation with Puppeteer chat automation
  // This is a scaffold - real implementation in Phase 1-2

  return {
    initialPrice: 0,
    finalPrice: 0,
    discountPct: 0,
    rounds: 0,
    messages: [],
    outcome: 'no_response',
  }
}
