import { cn } from '../../lib/utils.js'
import { Tooltip } from '../tooltip.js'

export type Currency = 'EUR' | 'USD' | 'CNY'

export interface MoneyValue {
  /** Unidades menores (céntimos, fen…) tal como llegan de la API. */
  amountMinor: bigint | number
  currency: Currency
}

export interface MoneyDisplayProps extends MoneyValue {
  locale: string
  size?: 'normal' | 'large'
  /** Importe original antes de convertir: se muestra en un tooltip accesible. */
  original?: MoneyValue
  /** Texto del tooltip antes del importe original, ya traducido. Sin él no hay tooltip. */
  originalLabel?: string
  className?: string
}

/** Solo formatea. BigInt separa la parte entera y los dos decimales: sin coma flotante. */
function moneyParts(value: MoneyValue, locale: string): Intl.NumberFormatPart[] {
  const minor =
    typeof value.amountMinor === 'bigint' ? value.amountMinor : BigInt(value.amountMinor)
  const neg = minor < 0n
  const abs = neg ? -minor : minor
  const fmt = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: value.currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  const cents = (abs % 100n).toString().padStart(2, '0')
  const parts = fmt
    .formatToParts(abs / 100n)
    .map((p) => (p.type === 'fraction' ? { ...p, value: cents } : p))
  return neg ? [{ type: 'minusSign', value: '−' }, ...parts] : parts
}

/** Importe de la API. Cifras tabulares, importe grande y divisa pequeña. */
export function MoneyDisplay({
  amountMinor,
  currency,
  locale,
  size = 'normal',
  original,
  originalLabel,
  className,
}: MoneyDisplayProps) {
  const body = (
    <span
      className={cn(
        'whitespace-nowrap tabular-nums',
        size === 'large' && 'text-[40px] leading-[1.1] font-semibold tracking-[-0.02em]',
        className
      )}
    >
      {moneyParts({ amountMinor, currency }, locale).map((p, i) => (
        <span key={i} className={p.type === 'currency' ? 'text-ink-muted text-[13px]' : undefined}>
          {p.value}
        </span>
      ))}
    </span>
  )
  if (!original || !originalLabel) return body
  const originalText = moneyParts(original, locale)
    .map((p) => p.value)
    .join('')
  return (
    <Tooltip text={`${originalLabel} ${originalText}`}>
      <span tabIndex={0}>{body}</span>
    </Tooltip>
  )
}
