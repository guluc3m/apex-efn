// //todo_#164: sustituir por GET /v1/missions/{id}/recommendation?profile=… (órdenes, scores y explicación calculados por el backend)
import type { ConfidenceBand, FinancialVerdict, PriceBand, SignatureStatus } from '@apex/ui'

export type CriterionKey = 'price' | 'trust' | 'lead' | 'verdict'
export type ProfileKey = 'operative' | 'cfo'

export interface Finalist {
  id: string
  dealId: string
  name: string
  price: string
  /** Diferencia frente a la mediana, ya calculada. */
  delta: { label: string; dir: 'down' | 'up' }
  note?: string
  priceBand: PriceBand
  confidence: { band: ConfidenceBand; score: number }
  verdict: FinancialVerdict
  signature: SignatureStatus
  landed: string
  lead: string
}

export interface RankedFinalist {
  id: string
  score: string
  /** Contribución por criterio; solo para dibujar, la suma ya viene en `score`. */
  parts: Record<CriterionKey, number>
  vsFirst: string
}

export interface CompareFixture {
  missionCode: string
  median: string
  finalists: Finalist[]
  profiles: Record<ProfileKey, { headline: string; explanation: string; ranking: RankedFinalist[] }>
  savings: { list: string; median: string; year: string; category: string; memory: string }
}

export const COMPARE: CompareFixture = {
  missionCode: 'M-0142',
  median: '1,80 €',
  finalists: [
    { id: 'a', dealId: 'd-0142-a', name: 'Vendedor A', price: '1,72 €', delta: { label: '−4 %', dir: 'down' }, priceBand: 'normal', confidence: { band: 'high', score: 86 }, verdict: 'within_budget', signature: 'pending', landed: '9.842,00 €', lead: '12 días' },
    { id: 'k', dealId: 'd-0142-k', name: 'Vendedor K', price: '1,64 €', delta: { label: '−9 %', dir: 'down' }, priceBand: 'normal', confidence: { band: 'low', score: 38 }, verdict: 'within_budget', signature: 'pending', landed: '9.610,00 €', lead: '30 días' },
    { id: 'j', dealId: 'd-0142-j', name: 'Vendedor J', price: '1,95 €', delta: { label: '+8 %', dir: 'up' }, note: 'Abortada · ronda 1', priceBand: 'normal', confidence: { band: 'high', score: 79 }, verdict: 'stretch', signature: 'pending', landed: '11.020,00 €', lead: '9 días' },
  ],
  profiles: {
    operative: {
      headline: 'Vendedor A gana por confianza; J entrega antes y K es más barato',
      explanation: 'Perfil operativo: pesa la confianza del vendedor y el plazo por encima del precio unitario.',
      ranking: [
        { id: 'a', score: '0,78', parts: { price: 0.22, trust: 0.26, lead: 0.16, verdict: 0.14 }, vsFirst: '' },
        { id: 'k', score: '0,61', parts: { price: 0.26, trust: 0.1, lead: 0.08, verdict: 0.17 }, vsFirst: '232 € más barato, pero 18 días más de plazo y confianza baja: necesita desbloqueo firmado.' },
        { id: 'j', score: '0,59', parts: { price: 0.1, trust: 0.24, lead: 0.19, verdict: 0.06 }, vsFirst: '3 días antes, pero 1.178 € más caro y al límite del envelope.' },
      ],
    },
    cfo: {
      headline: 'Vendedor A gana también para finanzas; J pasa por delante de K por el riesgo de confianza',
      explanation: 'Perfil CFO: pesa el veredicto financiero y la confianza; el plazo cuenta menos. La confianza baja de K lo deja en 3.º.',
      ranking: [
        { id: 'a', score: '0,80', parts: { price: 0.2, trust: 0.3, lead: 0.1, verdict: 0.2 }, vsFirst: '' },
        { id: 'j', score: '0,60', parts: { price: 0.08, trust: 0.26, lead: 0.14, verdict: 0.12 }, vsFirst: '3 días antes, pero 1.178 € más caro y al límite del envelope.' },
        { id: 'k', score: '0,52', parts: { price: 0.24, trust: 0.08, lead: 0.05, verdict: 0.15 }, vsFirst: '232 € más barato, pero 18 días más de plazo y confianza baja: necesita desbloqueo firmado.' },
      ],
    },
  },
  savings: { list: '450,00 €', median: '400,00 €', year: '3.180,00 €', category: 'Rodamientos', memory: 'La última vez, en marzo, Vendedor A te lo dejó en 1,75 €/ud.' },
}
