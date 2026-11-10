import type { ConvertedMoney, Currency, FxRate } from '@apex/shared-types/contracts'
import { CURRENCY_MINOR_UNITS } from '@apex/shared-types/currency'

import { divideHalfAwayFromZero, Money, MoneyError, parseDecimal } from './money.js'

/**
 * FX conversion with the EUR pivot (ADR-302). Mirrors `apex.domain.fx.convert` for previews; the
 * orchestrator stays authoritative. Rates are decimal strings applied as exact rationals.
 */

const PIVOT: Currency = 'EUR' // fx.pivot is global and closed (ADR-900 Q13)
const RATE_DECIMALS = 12n // fx_rates.rate is Decimal(24, 12)

export type FxErrorCode = 'rate_unavailable' | 'invalid_rate'

export class FxError extends Error {
  constructor(
    readonly code: FxErrorCode,
    message: string
  ) {
    super(message)
    this.name = 'FxError'
  }
}

export interface FxConfig {
  /** `fx.max_age_hours` from the effective tenant config */
  maxAgeHours: number
}

/** An exact positive rational. */
interface Ratio {
  num: bigint
  den: bigint
}

interface Path {
  rate: Ratio
  asOf: string
  time: number
  kind: number // 0 direct, 1 inverse, 2 triangulated: the tie-break order
  source: string
}

function value(rate: FxRate): Ratio {
  let parsed: Ratio = { num: 0n, den: 1n }
  try {
    parsed = parseDecimal(rate.rate)
  } catch (e) {
    if (!(e instanceof MoneyError)) throw e
  }
  if (parsed.num <= 0n) {
    throw new FxError(
      'invalid_rate',
      `Rate must be a positive decimal string: ${String(rate.rate)}`
    )
  }
  return parsed
}

/** Every `src→dst` rate keyed by as_of and source, direct preferred over inverse. */
function legs(rates: FxRate[], src: Currency, dst: Currency): Map<string, Path> {
  const found = new Map<string, Path>()
  const add = (r: FxRate, rate: Ratio, kind: number) => {
    const time = Date.parse(r.as_of)
    found.set(`${time}|${r.source}`, { rate, asOf: r.as_of, time, kind, source: r.source })
  }
  for (const r of rates) {
    if (r.base === dst && r.quote === src) {
      const v = value(r)
      add(r, { num: v.den, den: v.num }, 1)
    }
  }
  for (const r of rates) if (r.base === src && r.quote === dst) add(r, value(r), 0)
  return found
}

function paths(rates: FxRate[], src: Currency, dst: Currency): Path[] {
  const all = [...legs(rates, src, dst).values()]
  if (src !== PIVOT && dst !== PIVOT) {
    const second = legs(rates, PIVOT, dst)
    for (const [key, a] of legs(rates, src, PIVOT)) {
      const b = second.get(key)
      if (b) {
        const rate = { num: a.rate.num * b.rate.num, den: a.rate.den * b.rate.den }
        all.push({ ...a, rate, kind: 2 })
      }
    }
  }
  return all
}

function rateString({ num, den }: Ratio): string {
  const unit = 10n ** RATE_DECIMALS
  const scaled = divideHalfAwayFromZero(num * unit, den)
  const fraction = (scaled % unit).toString().padStart(Number(RATE_DECIMALS), '0')
  return `${scaled / unit}.${fraction}`.replace(/0+$/, '').replace(/\.$/, '')
}

const compare = (a: Path, b: Path) =>
  b.time - a.time || a.kind - b.kind || (a.source < b.source ? -1 : a.source > b.source ? 1 : 0)

/** Convert with the freshest usable path (ADR-302 §2); stale paths are flagged, never dropped. */
export function convert(
  money: Money,
  to: Currency,
  rates: FxRate[],
  now: string,
  cfg: FxConfig
): ConvertedMoney {
  const target = Money.zero(to).currency
  if (target === money.currency) {
    return {
      amount_minor: money.amountMinor,
      currency: target,
      original_amount_minor: null,
      original_currency: null,
      fx_rate: null,
      fx_as_of: null,
      fx_source: null,
      converted: false,
      fx_provisional: false,
    }
  }
  const nowMs = Date.parse(now)
  const usable = rates.filter((r) => Date.parse(r.as_of) <= nowMs)
  const best = paths(usable, money.currency, target).sort(compare)[0]
  if (!best) {
    throw new FxError('rate_unavailable', `No usable ${money.currency}->${target} rate at ${now}`)
  }
  const num = BigInt(money.amountMinor) * best.rate.num * BigInt(CURRENCY_MINOR_UNITS[target])
  const den = best.rate.den * BigInt(CURRENCY_MINOR_UNITS[money.currency])
  return {
    amount_minor: Money.fromMinor(Number(divideHalfAwayFromZero(num, den)), target).amountMinor,
    currency: target,
    original_amount_minor: money.amountMinor,
    original_currency: money.currency,
    fx_rate: rateString(best.rate),
    fx_as_of: best.asOf,
    fx_source: best.source,
    converted: true,
    fx_provisional: nowMs - best.time > cfg.maxAgeHours * 3_600_000,
  }
}
