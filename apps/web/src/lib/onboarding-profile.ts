import type { UpdateOnboardingSessionData } from '@apex/shared-types'

import type { Drafts } from '@/components/onboarding/schemas'

type Patch = UpdateOnboardingSessionData['body']['company_profile']

// Only these two steps map to the CompanyProfile contract; the rest are config (signed decisions).
const FREQUENCY = { monthly: 'monthly', quarterly: 'quarterly', occasional: 'one_off' } as const

export function toProfilePatch(step: 'empresa' | 'sector', d: Drafts): Patch {
  if (step === 'empresa') {
    const e = d.empresa
    return {
      legal_name: e.razonSocial,
      tax_id: e.cif,
      country: e.pais.toUpperCase(),
      customs_regime: e.aduana,
      shipping_address: e.direccion,
      ...(e.facturacionIgual ? { billing_address: e.direccion } : {}),
    }
  }
  const s = d.sector
  return {
    cnae: s.cnae,
    purchase_frequency: FREQUENCY[s.frecuencia as keyof typeof FREQUENCY] ?? null,
    purchase_categories: s.compras
      .split(/[,\n]/)
      .map((c) => c.trim())
      .filter(Boolean),
    seasonality: s.estacionalidad || null,
  }
}
