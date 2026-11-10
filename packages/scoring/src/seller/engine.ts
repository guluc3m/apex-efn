import type {
  ReviewAnomaly,
  ReviewAnomalyType,
  SellerConfidence,
  SellerConfidenceBand,
  SellerSignalSnapshot,
} from '@apex/shared-types/contracts'

/**
 * Seller confidence (D3-06, spec §3.4.2, ADR-303, ADR-304). Mirror of `apex.domain.trust.compute`, which is
 * the authority: same operations in the same order, so both pass `packages/test-vectors/trust`.
 */

export const ENGINE_VERSION = 'seller-confidence@1'
const GROUPS = ['age', 'sales', 'catalog', 'reviews', 'institutional'] as const
const COUNT_SIGNALS = [
  'lifetime_transactions',
  'transactions_12m',
  'gmv_12m',
  'published_products_count',
  'reviews_total',
  'reviews_12m',
] as const
/** The 21 raw signals of spec §3.4.1. `seller.min_signals` counts the present ones (ADR-303). */
export const RAW_SIGNALS = [
  'account_age_days',
  'first_sale_date',
  'months_active_last_12',
  'lifetime_transactions',
  'transactions_12m',
  'gmv_12m',
  'repeat_buyer_share',
  'published_products_count',
  'catalog_churn_30d',
  'spec_completeness_avg',
  'reviews_total',
  'reviews_12m',
  'rating_avg',
  'rating_count',
  'verified_review_share',
  'response_rate',
  'identity_verified',
  'trade_assurance',
  'escrow_available',
  'dispute_rate',
  'refund_rate',
] as const
type Group = (typeof GROUPS)[number]
/** Scored signals per group (ADR-304). An absent signal scores 0: missing data never helps. */
const GROUP_SIGNALS: Record<Group, readonly string[]> = {
  age: ['account_age_days', 'first_sale_date', 'months_active_last_12'],
  sales: ['lifetime_transactions', 'transactions_12m', 'gmv_12m', 'repeat_buyer_share'],
  catalog: ['published_products_count', 'catalog_churn_30d', 'spec_completeness_avg'],
  reviews: [
    'rating_adjusted',
    'positive_share_wilson',
    'reviews_total',
    'reviews_12m',
    'verified_review_share',
    'response_rate',
  ],
  institutional: ['identity_verified', 'trade_assurance', 'escrow_available'],
}
const BUCKET_DAYS = 30 // review-velocity bucket (ADR-303)
const BURST_BUCKETS = 12
const DAY_MS = 86_400_000

export type TrustErrorCode = 'config_unset' | 'config_invalid' | 'gmv_not_eur'

export class TrustError extends Error {
  constructor(
    readonly code: TrustErrorCode,
    message: string
  ) {
    super(message)
    this.name = 'TrustError'
  }
}

/** One review as the adapter saw it. The engine reads structure, never meaning. */
export interface Review {
  rating: number
  /** YYYY-MM-DD */
  date: string
  verified: boolean
  text?: string
}

export interface TrustConfig {
  configVersion: string
  weights: Record<Group, number>
  xSat: Record<(typeof COUNT_SIGNALS)[number], number>
  ratingPriorWeight: number
  categoryRatingMean: number
  wilsonConfidence: number
  ageSaturationDays: number
  minSignals: number
  bandHigh: number
  bandMedium: number
  bandLow: number
  hardBlockBelow: number
  reviewBurstZ: number
  categoryFiveStarShare: number
  minVerifiedShare: number
  maxDuplicateTextShare: number
  maxDisputeRate: number
}

/** Exact check that decimal literals add up to 1 (Python uses `Decimal`). */
function decimalSumIsOne(values: unknown[]): boolean {
  const parts = values.map((v) => String(v).split('.'))
  const scale = Math.max(...parts.map((p) => (p[1] ?? '').length))
  const total = parts.reduce((acc, [i = '0', f = '']) => acc + BigInt(i + f.padEnd(scale, '0')), 0n)
  return total === 10n ** BigInt(scale)
}

/** Builds the config from the `seller.*` slice. Unset values refuse to run: no default is invented. */
export function trustConfigFrom(
  seller: Record<string, unknown>,
  configVersion: string
): TrustConfig {
  const need = (key: string): unknown => {
    const v = seller[key]
    if (v === null || v === undefined)
      throw new TrustError('config_unset', `seller.${key} is unset`)
    return v
  }
  const toNum = (key: string, v: unknown): number => {
    const n = typeof v === 'number' || typeof v === 'string' ? Number(v) : NaN
    if (!Number.isFinite(n)) throw new TrustError('config_invalid', `seller.${key} is not a number`)
    return n
  }
  const num = (key: string) => toNum(key, need(key))
  const table = <K extends string>(key: string, keys: readonly K[]): Record<K, number> => {
    const raw = need(key)
    const given = typeof raw === 'object' && raw !== null ? Object.keys(raw) : []
    if (given.length !== keys.length || !keys.every((k) => given.includes(k)))
      throw new TrustError(
        'config_invalid',
        `seller.${key} must have exactly ${[...keys].sort().join(', ')}`
      )
    const values = raw as Record<K, unknown>
    for (const k of keys)
      if (values[k] === null || values[k] === undefined)
        throw new TrustError('config_unset', `seller.${key}.${k} is unset`)
    const out = {} as Record<K, number>
    for (const k of keys) out[k] = toNum(`${key}.${k}`, values[k])
    if (Object.values<number>(out).some((v) => v < 0))
      throw new TrustError('config_invalid', `seller.${key} values must be non-negative`)
    if (key === 'weights' && !decimalSumIsOne(keys.map((k) => values[k])))
      throw new TrustError('config_invalid', 'seller.weights must sum to exactly 1')
    return out
  }
  const cfg: TrustConfig = {
    configVersion,
    weights: table('weights', GROUPS),
    xSat: table('x_sat', COUNT_SIGNALS),
    ratingPriorWeight: num('rating_prior_weight'),
    categoryRatingMean: num('category_rating_mean'),
    wilsonConfidence: num('wilson_confidence'),
    ageSaturationDays: num('age_saturation_days'),
    minSignals: Math.trunc(num('min_signals')),
    bandHigh: Math.trunc(num('band_high')),
    bandMedium: Math.trunc(num('band_medium')),
    bandLow: Math.trunc(num('band_low')),
    hardBlockBelow: Math.trunc(num('hard_block_below')),
    reviewBurstZ: num('review_burst_z'),
    categoryFiveStarShare: num('category_five_star_share'),
    minVerifiedShare: num('min_verified_share'),
    maxDuplicateTextShare: num('max_duplicate_text_share'),
    maxDisputeRate: num('max_dispute_rate'),
  }
  if (Object.values(cfg.xSat).some((v) => v <= 0) || cfg.ageSaturationDays <= 0)
    throw new TrustError('config_invalid', 'saturation points must be positive')
  const open01 = (v: number) => v > 0 && v < 1
  if (!open01(cfg.wilsonConfidence) || !open01(cfg.categoryFiveStarShare))
    throw new TrustError(
      'config_invalid',
      'wilson_confidence and category_five_star_share are in (0, 1)'
    )
  if (cfg.categoryRatingMean < 1 || cfg.categoryRatingMean > 5 || cfg.maxDisputeRate <= 0)
    throw new TrustError(
      'config_invalid',
      'category_rating_mean is in [1, 5], max_dispute_rate > 0'
    )
  if (!(cfg.bandLow <= cfg.bandMedium && cfg.bandMedium <= cfg.bandHigh))
    throw new TrustError(
      'config_invalid',
      'bands must satisfy band_low <= band_medium <= band_high'
    )
  return cfg
}

// Wichura AS241 with the constants of CPython's statistics.NormalDist.inv_cdf, highest power first.
// Copied verbatim: both languages round them to the same doubles.
/* eslint-disable no-loss-of-precision */
const AS241 = {
  a: [
    2.5090809287301226727e3, 3.3430575583588128105e4, 6.7265770927008700853e4,
    4.5921953931549871457e4, 1.3731693765509461125e4, 1.9715909503065514427e3,
    1.3314166789178437745e2, 3.387132872796366608,
  ],
  b: [
    5.226495278852854561e3, 2.8729085735721942674e4, 3.930789580009271061e4,
    2.1213794301586595867e4, 5.3941960214247511077e3, 6.871870074920579083e2,
    4.2313330701600911252e1, 1.0,
  ],
  c: [
    7.7454501427834140764e-4, 2.27238449892691845833e-2, 2.4178072517745061177e-1,
    1.27045825245236838258, 3.64784832476320460504, 5.7694972214606914055, 4.6303378461565452959,
    1.42343711074968357734,
  ],
  d: [
    1.05075007164441684324e-9, 5.475938084995344946e-4, 1.51986665636164571966e-2,
    1.4810397642748007459e-1, 6.8976733498510000455e-1, 1.6763848301838038494,
    2.05319162663775882187, 1.0,
  ],
  e: [
    2.01033439929228813265e-7, 2.71155556874348757815e-5, 1.2426609473880784386e-3,
    2.6532189526576123093e-2, 2.9656057182850489123e-1, 1.7848265399172913358,
    5.4637849111641143699, 6.6579046435011037772,
  ],
  f: [
    2.04426310338993978564e-15, 1.4215117583164458887e-7, 1.8463183175100546818e-5,
    7.868691311456132591e-4, 1.48753612908506148525e-2, 1.3692988092273580531e-1,
    5.9983220655588793769e-1, 1.0,
  ],
}
/* eslint-enable no-loss-of-precision */
const horner = (cs: number[], r: number) => cs.slice(1).reduce((acc, c) => acc * r + c, cs[0]!)

/** Inverse standard normal CDF, bit-compatible with Python's `NormalDist().inv_cdf`. */
export function normalInvCdf(p: number): number {
  const q = p - 0.5
  if (Math.abs(q) <= 0.425) {
    const r = 0.180625 - q * q
    return (horner(AS241.a, r) * q) / horner(AS241.b, r)
  }
  let r = Math.sqrt(-Math.log(q <= 0 ? p : 1 - p))
  const tail = r <= 5.0
  r = tail ? r - 1.6 : r - 5.0
  const x = tail ? horner(AS241.c, r) / horner(AS241.d, r) : horner(AS241.e, r) / horner(AS241.f, r)
  return q < 0 ? -x : x
}

const logSat = (x: number, xSat: number) => Math.min(Math.log10(1 + x) / Math.log10(1 + xSat), 1.0)
const linSat = (x: number, xSat: number) => Math.min(Math.max(x, 0) / xSat, 1.0)
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)
/** Whole days between two YYYY-MM-DD dates, like Python's `(to - from).days`. */
const days = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / DAY_MS)

function wilsonLower(positive: number, n: number, z: number): number {
  const p = positive / n
  const z2 = z * z
  const centre = p + z2 / (2 * n)
  const margin = z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))
  return (centre - margin) / (1 + z2 / n)
}

/** z of `peak` against the population mean/sd of `rest`. sd is floored at 1 review (ADR-303). */
function zVsRest(peak: number, rest: number[]): number {
  const mean = sum(rest) / rest.length
  const sd = Math.sqrt(sum(rest.map((r) => (r - mean) * (r - mean))) / rest.length)
  return (peak - mean) / Math.max(sd, 1.0)
}

const signal = (s: SellerSignalSnapshot, name: string): unknown =>
  (s as unknown as Record<string, unknown>)[name] ?? null

function normalise(s: SellerSignalSnapshot, reviews: Review[] | null, cfg: TrustConfig) {
  const out: Record<string, number> = {}
  const captured = s.captured_at.slice(0, 10)
  if (s.account_age_days != null)
    out.account_age_days = linSat(s.account_age_days, cfg.ageSaturationDays)
  if (s.first_sale_date != null)
    out.first_sale_date = linSat(days(s.first_sale_date, captured), cfg.ageSaturationDays)
  if (s.months_active_last_12 != null) out.months_active_last_12 = s.months_active_last_12 / 12
  for (const name of COUNT_SIGNALS) {
    let value = signal(s, name) as number | { amount_minor: number; currency: string } | null
    if (value === null) continue
    if (typeof value === 'object') {
      if (value.currency !== 'EUR')
        throw new TrustError('gmv_not_eur', 'gmv_12m must be converted to EUR before scoring')
      value = value.amount_minor / 100 // x_sat.gmv_12m is in EUR (ADR-304)
    }
    out[name] = logSat(value, cfg.xSat[name])
  }
  for (const name of [
    'repeat_buyer_share',
    'spec_completeness_avg',
    'verified_review_share',
    'response_rate',
  ]) {
    const value = signal(s, name) as number | null
    if (value !== null) out[name] = value
  }
  if (s.catalog_churn_30d != null) out.catalog_churn_30d = 1 - s.catalog_churn_30d
  if (s.rating_avg != null) {
    const n = s.rating_count ?? 0
    const c = cfg.ratingPriorWeight
    const adjusted = (c * cfg.categoryRatingMean + s.rating_avg * n) / (c + n)
    out.rating_adjusted = (adjusted - 1) / 4
  }
  if (reviews?.length) {
    const z = normalInvCdf(1 - (1 - cfg.wilsonConfidence) / 2)
    const positive = reviews.filter((r) => r.rating >= 4).length
    out.positive_share_wilson = wilsonLower(positive, reviews.length, z)
  }
  for (const name of ['identity_verified', 'trade_assurance', 'escrow_available']) {
    const value = signal(s, name) as boolean | null
    if (value !== null) out[name] = value ? 1.0 : 0.0
  }
  return out
}

function flagsFor(
  s: SellerSignalSnapshot,
  reviews: Review[] | null,
  cfg: TrustConfig,
  now: string
) {
  const flags: ReviewAnomaly[] = []
  // Every flag caps the band, so every flag is critical (ADR-303).
  const flag = (type: ReviewAnomalyType, evidence: Record<string, number>) =>
    flags.push({ seller_id: s.seller_id, type, severity: 'critical', evidence, detected_at: now })
  if (s.verified_review_share != null && s.verified_review_share < cfg.minVerifiedShare)
    flag('low_verified_share', {
      verified_review_share: s.verified_review_share,
      threshold: cfg.minVerifiedShare,
    })
  if (!reviews?.length) return flags
  const captured = s.captured_at.slice(0, 10)

  const buckets: number[] = Array<number>(BURST_BUCKETS).fill(0)
  for (const r of reviews) {
    const age = days(r.date, captured)
    if (age >= 0 && age < BUCKET_DAYS * BURST_BUCKETS) buckets[Math.floor(age / BUCKET_DAYS)]! += 1
  }
  const peak = Math.max(...buckets)
  const rest = [...buckets]
  rest.splice(rest.indexOf(peak), 1)
  let z = zVsRest(peak, rest)
  if (z > cfg.reviewBurstZ) flag('burst_velocity', { peak_bucket_reviews: peak, z })

  const n = reviews.length
  const p0 = cfg.categoryFiveStarShare
  const five = reviews.filter((r) => r.rating === 5).length
  z = (five / n - p0) / Math.sqrt((p0 * (1 - p0)) / n)
  if (z > cfg.reviewBurstZ) flag('five_star_anomaly', { five_star_share: five / n, z })

  const texts = reviews
    .map((r) => (r.text ?? '').toLowerCase().split(/\s+/).filter(Boolean).join(' '))
    .filter(Boolean)
  if (texts.length) {
    const counts = new Map<string, number>()
    for (const t of texts) counts.set(t, (counts.get(t) ?? 0) + 1)
    const share = texts.filter((t) => counts.get(t)! > 1).length / texts.length
    if (share > cfg.maxDuplicateTextShare) flag('duplicate_text', { duplicate_share: share })
  }

  const age = s.account_age_days
  if (age != null && Math.floor(age / BUCKET_DAYS) >= 3) {
    const created = new Date(Date.parse(captured) - age * DAY_MS).toISOString().slice(0, 10)
    const life: number[] = Array<number>(Math.floor(age / BUCKET_DAYS)).fill(0)
    for (const r of reviews) {
      const k = Math.floor(days(created, r.date) / BUCKET_DAYS)
      if (k >= 0 && k < life.length) life[k]! += 1
    }
    z = zVsRest(life[0]!, life.slice(1))
    if (z > cfg.reviewBurstZ) flag('creation_correlation', { first_bucket_reviews: life[0]!, z })
  }
  return flags
}

function bandFor(score: number, cfg: TrustConfig): SellerConfidenceBand {
  if (score < cfg.bandLow || score < cfg.hardBlockBelow) return 'untrusted'
  if (score >= cfg.bandHigh) return 'high'
  if (score >= cfg.bandMedium) return 'medium'
  return 'low'
}

/** Seller confidence from one immutable snapshot. `now` (ISO-8601) only stamps `computed_at`. */
export function computeSellerConfidence(
  snapshot: SellerSignalSnapshot,
  cfg: TrustConfig,
  now: string,
  reviews: Review[] | null = null
): SellerConfidence {
  const base = {
    seller_id: snapshot.seller_id,
    model_version: `${ENGINE_VERSION}/${cfg.configVersion}`,
    snapshot_id: snapshot.id,
    computed_at: now,
  }
  const present = RAW_SIGNALS.filter((name) => signal(snapshot, name) !== null).length
  if (present < cfg.minSignals)
    return {
      ...base,
      score: null,
      band: 'insufficient_data',
      signals_normalized: {},
      penalties: [],
      flags: [],
    }

  const normalized = normalise(snapshot, reviews, cfg)
  let total = 0
  for (const group of GROUPS) {
    const signals = GROUP_SIGNALS[group]
    total += cfg.weights[group] * (sum(signals.map((n) => normalized[n] ?? 0)) / signals.length)
  }
  const penalties = reviews?.length ? [] : ['reviews_unavailable']
  let worst = 0
  for (const name of ['dispute_rate', 'refund_rate']) {
    const rate = signal(snapshot, name) as number | null
    if (rate !== null && rate > cfg.maxDisputeRate) {
      penalties.push(`${name}_above_max`)
      worst = Math.max(worst, rate)
    }
  }
  if (worst) total *= cfg.maxDisputeRate / worst // proportional penalty (ADR-304)

  const score = Math.floor(100 * total + 0.5)
  let band = bandFor(score, cfg)
  const flags = flagsFor(snapshot, reviews, cfg, now)
  if (flags.length && (band === 'high' || band === 'medium')) band = 'low'
  return { ...base, score, band, signals_normalized: normalized, penalties, flags }
}
