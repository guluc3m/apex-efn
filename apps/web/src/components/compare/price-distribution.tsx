'use client'

import type { Offer, PriceSanityBand } from '@apex/shared-types/contracts'
import { useLocale, useTranslations } from 'next-intl'
import { Bar, BarChart, Cell, ReferenceArea, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'

const FILL: Record<PriceSanityBand, string> = {
  normal: 'var(--accent)',
  atypical: 'var(--warn)',
  implausible: 'var(--bad)',
  insufficient_reference: 'var(--ink-muted)',
}

/** Unit price of every offer with the market median marked. Band and median come from each offer's PriceSanityCheck. */
export function PriceDistribution({ offers }: { offers: readonly Offer[] }) {
  const t = useTranslations('compare.distribution')
  const tb = useTranslations('compare.price')
  const locale = useLocale()
  const checked = offers.filter((o) => o.price_sanity_check)
  if (checked.length === 0) return <p className="m-0 text-[13px] text-ink-muted">{t('none')}</p>

  // An `insufficient_reference` check echoes the offer's own price back as median and zero deviation:
  // it is not a market reference, so the chart must not draw it. Prefer the first offer with a real one.
  const first = (checked.find((o) => o.price_sanity_check!.band !== 'insufficient_reference') ?? checked[0]!).price_sanity_check!
  const hasReference = first.band !== 'insufficient_reference'
  const currency = checked[0]!.unit_price.currency
  // Chart axis only: minor units to major for formatting, never for any business result.
  const money = new Intl.NumberFormat(locale, { style: 'currency', currency })
  const nf = new Intl.NumberFormat(locale)
  const toMajor = (minor: number) => minor / 100
  // The sanity check may omit the reference numbers until there is enough of a sample (provisional API).
  const median = hasReference ? first.median?.amount_minor : undefined
  // Normal band as the server computed it; absent when there was no reference to compute it from.
  const lower = hasReference ? first.band_lower?.amount_minor : undefined
  const upper = hasReference ? first.band_upper?.amount_minor : undefined
  const hasBand = lower != null && upper != null
  // Sample size and dispersion measure name the reference the band came from; omit what the API omits.
  const sample = first.sample_size
  const measure = hasReference && first.dispersion_measure ? t(`dispersion.${first.dispersion_measure}`) : null
  const stats =
    sample != null && measure
      ? t('stats', { sample: nf.format(sample), measure })
      : sample != null
        ? t('statsSample', { sample: nf.format(sample) })
        : measure
          ? t('statsDispersion', { measure })
          : null
  const data = [...checked]
    .sort((a, b) => a.unit_price.amount_minor - b.unit_price.amount_minor)
    .map((o) => ({ id: o.id, name: o.seller_name, price: o.unit_price.amount_minor, band: o.price_sanity_check!.band }))

  return (
    <figure className="m-0 flex flex-col gap-2">
      <figcaption className="text-[13px] text-ink-muted">
        {median == null
          ? t('captionNoMedian')
          : hasBand
            ? t('captionBand', { median: money.format(toMajor(median)), lower: money.format(toMajor(lower)), upper: money.format(toMajor(upper)) })
            : t('caption', { median: money.format(toMajor(median)) })}
        {stats && <span className="block tabular-nums">{stats}</span>}
      </figcaption>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
            <XAxis dataKey="name" tick={{ fill: 'var(--ink-muted)', fontSize: 13 }} stroke="var(--line-strong)" />
            <YAxis hide domain={[0, 'auto']} />
            {hasBand && <ReferenceArea y1={lower} y2={upper} fill="var(--accent)" fillOpacity={0.12} stroke="none" />}
            {median != null && <ReferenceLine y={median} stroke="var(--ink)" strokeDasharray="4 3" />}
            <Bar dataKey="price" isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.id} fill={FILL[d.band]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="m-0 flex flex-wrap gap-x-4 gap-y-1 p-0 text-[13px]">
        {data.map((d) => (
          <li key={d.id} className="flex list-none items-center gap-1.5">
            <span className="inline-block size-3" style={{ background: FILL[d.band] }} aria-hidden="true" />
            {d.name}: {money.format(toMajor(d.price))} · {tb(d.band)}
          </li>
        ))}
      </ul>
    </figure>
  )
}
