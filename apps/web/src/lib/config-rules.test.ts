import type { EffectiveConfig } from '@apex/shared-types/contracts'
import { describe, expect, it } from 'vitest'

import { parsePatchValue, toRuleRows } from './config-rules'

const cfg = {
  tenant_id: 't',
  category: null,
  config_version: 3,
  content_hash: 'sha256:' + '0'.repeat(64),
  resolved_at: '2026-11-10T00:00:00Z',
  values: {
    'signing.session_minutes': { value: 15, status: 'set', layer: 'global' },
    'approval.dual_control_above': { value: null, status: 'unset', layer: 'tenant' },
    'sanity.floor_per_unit': { value: { amount_minor: 125, currency: 'EUR' }, status: 'set', layer: 'category' },
    'neg.max_rounds': { value: 0, status: 'unset', layer: 'tenant' },
  },
} as EffectiveConfig

describe('toRuleRows', () => {
  const rows = toRuleRows(cfg, 'en')
  const by = (k: string) => rows.find((r) => r.key === k)!
  it('keeps unset values as null, never 0', () => {
    expect(by('approval.dual_control_above').display).toBeNull()
    expect(by('neg.max_rounds').display).toBeNull()
  })
  it('formats numbers and money, groups by prefix', () => {
    expect(by('signing.session_minutes').display).toBe('15')
    expect(by('sanity.floor_per_unit').display).toContain('1.25')
    expect(by('neg.max_rounds').group).toBe('neg')
  })
})

describe('parsePatchValue', () => {
  it('parses JSON and falls back to text', () => {
    expect(parsePatchValue('5.5')).toBe(5.5)
    expect(parsePatchValue('null')).toBeNull()
    expect(parsePatchValue('go_gate')).toBe('go_gate')
  })
})
