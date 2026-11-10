import type { EffectiveConfig } from '@apex/shared-types/contracts'

export interface RuleRow {
  key: string
  group: string
  /** null means unset ("sin definir"): never shown as 0 or empty. */
  display: string | null
  layer: 'global' | 'tenant' | 'category'
}

/** Format only: the server decides every value. Money minor units are shown with the currency's own exponent (all three are 2). */
export function formatConfigValue(value: unknown, locale: string): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'object' && 'amount_minor' in value && 'currency' in value) {
    const m = value as { amount_minor: number | string; currency: string }
    return new Intl.NumberFormat(locale, { style: 'currency', currency: m.currency }).format(Number(m.amount_minor) / 100)
  }
  if (typeof value === 'number') return new Intl.NumberFormat(locale, { maximumFractionDigits: 6 }).format(value)
  if (typeof value === 'object') return JSON.stringify(value)
  return typeof value === 'string' ? value : JSON.stringify(value)
}

/** Rows sorted by key. A key whose status is `unset` is unset even if the server sent a value. */
export function toRuleRows(config: EffectiveConfig, locale: string): RuleRow[] {
  return Object.entries(config.values)
    .map(([key, v]) => ({
      key,
      group: key.split('.')[0] ?? key,
      display: v.status === 'unset' ? null : formatConfigValue(v.value, locale),
      layer: v.layer,
    }))
    .sort((a, b) => a.key.localeCompare(b.key))
}

/** Roles allowed to propose a rule change (AGENTS.md: finance|admin|owner). */
export const RULE_CHANGE_ROLES: readonly string[] = ['finance', 'admin', 'owner']

/** The patch value the user typed: JSON when it parses (numbers, booleans, null to unset), plain text otherwise. */
export function parsePatchValue(input: string): unknown {
  const s = input.trim()
  try {
    return JSON.parse(s)
  } catch {
    return s
  }
}
