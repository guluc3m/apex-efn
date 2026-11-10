import { describe, expect, it } from 'vitest'

import { initialDrafts } from '@/fixtures/onboarding'

import { toProfilePatch } from './onboarding-profile'

describe('toProfilePatch', () => {
  it('maps the company step and copies shipping to billing when equal', () => {
    const p = toProfilePatch('empresa', initialDrafts)
    expect(p).toMatchObject({
      country: 'ES',
      legal_name: 'Industrias Ejemplo, S.L.',
      billing_address: p?.shipping_address,
    })
  })
  it('maps the sector step to contract enums and a category list', () => {
    const p = toProfilePatch('sector', {
      ...initialDrafts,
      sector: { ...initialDrafts.sector, frecuencia: 'occasional', compras: 'a, b\nc' },
    })
    expect(p).toMatchObject({ purchase_frequency: 'one_off', purchase_categories: ['a', 'b', 'c'] })
  })
})
