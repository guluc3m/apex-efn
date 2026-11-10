import type { Offer, RankedOffer, Recommendation } from '@apex/shared-types/contracts'

export interface CompareRow {
  rank: number
  ranked: RankedOffer
  offer: Offer
  /** API-written summary of the trade-off against the first-ranked offer; null for #1 or when absent. */
  vsFirst: string | null
}

export interface CompareModel {
  rows: CompareRow[]
  /** Ranked ids the offers list did not contain (page cut off or stale); shown, never dropped silently. */
  missing: string[]
}

/** Joins the API ranking with the offers. Order and numbers are the API's; nothing is recomputed. */
export function buildCompareModel(rec: Recommendation, offers: readonly Offer[]): CompareModel {
  const byId = new Map(offers.map((o) => [o.id, o]))
  const first = rec.ranking[0]?.offer_id
  const rows: CompareRow[] = []
  const missing: string[] = []
  for (const ranked of rec.ranking) {
    const offer = byId.get(ranked.offer_id)
    if (!offer) {
      missing.push(ranked.offer_id)
      continue
    }
    const tradeOff =
      ranked.offer_id === first
        ? undefined
        : rec.alternatives?.find((a) => a.offer_id === ranked.offer_id && a.versus_offer_id === first)
    rows.push({ rank: ranked.rank, ranked, offer, vsFirst: tradeOff?.summary ?? null })
  }
  return { rows, missing }
}
