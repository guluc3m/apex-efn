import type { FinancialFit } from '@trato/shared-types/financial'
import type { Offer } from '@trato/shared-types/offer'
import type { SellerConfidence } from '@trato/shared-types/seller'

/**
 * MCDA weights configuration
 * All weights should sum to 1
 */
export interface MCDAWeights {
  landedCost: number
  leadTime: number
  sellerConfidence: number
  financialFit: number
  marginPotential: number
  specMatch: number
  complianceRisk: number
  negotiationGain: number
}

export interface MCDAConfig {
  weights: MCDAWeights
  // Normalization bounds for each criterion
  bounds: {
    maxLeadTimeDays: number
    maxLandedCostEur: number
  }
  modelVersion: string
}

export interface ScoredOffer {
  offerId: string
  totalScore: number
  breakdown: {
    criterion: keyof MCDAWeights
    rawValue: number
    normalizedValue: number
    weight: number
    contribution: number
  }[]
  rank: number
}

const DEFAULT_WEIGHTS: MCDAWeights = {
  landedCost: 0.25,
  leadTime: 0.1,
  sellerConfidence: 0.2,
  financialFit: 0.15,
  marginPotential: 0.1,
  specMatch: 0.1,
  complianceRisk: 0.05,
  negotiationGain: 0.05,
}

const DEFAULT_CONFIG: MCDAConfig = {
  weights: DEFAULT_WEIGHTS,
  bounds: {
    maxLeadTimeDays: 90,
    maxLandedCostEur: 1000000, // 10k EUR in cents
  },
  modelVersion: '1.0.0',
}

/**
 * Multi-Criteria Decision Analysis engine.
 * Implements section 3.7 of the spec.
 *
 * Uses a weighted sum model similar to TOPSIS.
 * All normalization functions are monotonic and documented.
 */
export class MCDAEngine {
  private readonly config: MCDAConfig

  constructor(config: Partial<MCDAConfig> = {}) {
    this.config = {
      ...DEFAULT_CONFIG,
      ...config,
      weights: { ...DEFAULT_WEIGHTS, ...config.weights },
    }

    // Validate weights sum to approximately 1
    const weightSum = Object.values(this.config.weights).reduce((a, b) => a + b, 0)
    if (Math.abs(weightSum - 1) > 0.001) {
      throw new Error(`Weights must sum to 1, got ${weightSum}`)
    }
  }

  /**
   * Score and rank a list of offers
   */
  scoreOffers(
    offers: Array<{
      offer: Offer
      confidence: SellerConfidence
      financialFit: FinancialFit
      negotiationGainPct?: number
      specMatchScore?: number
      complianceRiskScore?: number
    }>
  ): ScoredOffer[] {
    const scored = offers.map((item) => this.scoreOffer(item))

    // Sort by total score descending and assign ranks
    scored.sort((a, b) => b.totalScore - a.totalScore)
    scored.forEach((s, i) => {
      s.rank = i + 1
    })

    return scored
  }

  private scoreOffer(item: {
    offer: Offer
    confidence: SellerConfidence
    financialFit: FinancialFit
    negotiationGainPct?: number
    specMatchScore?: number
    complianceRiskScore?: number
  }): ScoredOffer {
    const { offer, confidence, financialFit, negotiationGainPct, specMatchScore, complianceRiskScore } =
      item
    const { weights, bounds } = this.config

    const breakdown: ScoredOffer['breakdown'] = []

    // 1. Landed cost (lower is better)
    const landedCostRaw = financialFit.landedCost.unitLandedCostMinor
    const landedCostNorm = 1 - Math.min(landedCostRaw / bounds.maxLandedCostEur, 1)
    breakdown.push({
      criterion: 'landedCost',
      rawValue: landedCostRaw,
      normalizedValue: landedCostNorm,
      weight: weights.landedCost,
      contribution: landedCostNorm * weights.landedCost,
    })

    // 2. Lead time (lower is better)
    const leadTimeRaw = offer.leadTimeDays ?? bounds.maxLeadTimeDays
    const leadTimeNorm = 1 - Math.min(leadTimeRaw / bounds.maxLeadTimeDays, 1)
    breakdown.push({
      criterion: 'leadTime',
      rawValue: leadTimeRaw,
      normalizedValue: leadTimeNorm,
      weight: weights.leadTime,
      contribution: leadTimeNorm * weights.leadTime,
    })

    // 3. Seller confidence (already 0-100, normalize to 0-1)
    const confidenceNorm = confidence.score / 100
    breakdown.push({
      criterion: 'sellerConfidence',
      rawValue: confidence.score,
      normalizedValue: confidenceNorm,
      weight: weights.sellerConfidence,
      contribution: confidenceNorm * weights.sellerConfidence,
    })

    // 4. Financial fit (verdict to score)
    const financialFitRaw =
      financialFit.verdict === 'within_budget' ? 1 : financialFit.verdict === 'stretch' ? 0.5 : 0
    breakdown.push({
      criterion: 'financialFit',
      rawValue: financialFitRaw,
      normalizedValue: financialFitRaw,
      weight: weights.financialFit,
      contribution: financialFitRaw * weights.financialFit,
    })

    // 5. Margin potential (placeholder, requires benchmark)
    const marginNorm = 0.5 // Default to neutral
    breakdown.push({
      criterion: 'marginPotential',
      rawValue: 0,
      normalizedValue: marginNorm,
      weight: weights.marginPotential,
      contribution: marginNorm * weights.marginPotential,
    })

    // 6. Spec match
    const specNorm = specMatchScore ?? 0.8
    breakdown.push({
      criterion: 'specMatch',
      rawValue: specNorm,
      normalizedValue: specNorm,
      weight: weights.specMatch,
      contribution: specNorm * weights.specMatch,
    })

    // 7. Compliance risk (lower is better)
    const complianceNorm = 1 - (complianceRiskScore ?? 0)
    breakdown.push({
      criterion: 'complianceRisk',
      rawValue: complianceRiskScore ?? 0,
      normalizedValue: complianceNorm,
      weight: weights.complianceRisk,
      contribution: complianceNorm * weights.complianceRisk,
    })

    // 8. Negotiation gain
    const negGainNorm = Math.min(negotiationGainPct ?? 0, 0.5) / 0.5 // Cap at 50%, normalize to 0-1
    breakdown.push({
      criterion: 'negotiationGain',
      rawValue: negotiationGainPct ?? 0,
      normalizedValue: negGainNorm,
      weight: weights.negotiationGain,
      contribution: negGainNorm * weights.negotiationGain,
    })

    // Calculate total score
    const totalScore = breakdown.reduce((sum, b) => sum + b.contribution, 0)

    return {
      offerId: offer.id,
      totalScore,
      breakdown,
      rank: 0, // Will be set after sorting
    }
  }

  get modelVersion(): string {
    return this.config.modelVersion
  }
}
