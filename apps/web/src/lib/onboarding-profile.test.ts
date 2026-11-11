import { describe, expect, it } from 'vitest'

import { initialDrafts } from '@/fixtures/onboarding'

import { fromProfile, restoreDrafts } from './onboarding-profile'

const empresa = initialDrafts.empresa

describe('fromProfile', () => {
  it('maps the agent-filled name and country onto the empresa draft', () => {
    expect(fromProfile({ legal_name: 'ACME S.L.', country: 'ES' }, empresa)).toEqual({ ...empresa, razonSocial: 'ACME S.L.', pais: 'ES' })
  })

  it('returns null when nothing changes, so the form is not remounted', () => {
    expect(fromProfile({ legal_name: null, country: null }, empresa)).toBeNull()
    expect(fromProfile({ legal_name: empresa.razonSocial, country: empresa.pais }, empresa)).toBeNull()
  })
})

describe('restoreDrafts', () => {
  it('restores what the server saved and keeps the rest of the draft', () => {
    const r = restoreDrafts({ legal_name: 'ACME', tax_id: 'B1', country: 'ES', purchase_frequency: 'one_off', purchase_categories: ['a', 'b'] }, initialDrafts)
    expect(r.empresa).toMatchObject({ razonSocial: 'ACME', cif: 'B1', pais: 'es', direccion: '' })
    expect(r.sector).toMatchObject({ frecuencia: 'occasional', compras: 'a, b', cnae: '' })
  })
})
