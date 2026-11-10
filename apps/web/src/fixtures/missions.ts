import type { ConfidenceBand, FinancialVerdict, PriceBand, SignatureStatus } from '@apex/ui'

// Datos del lienzo (Peticion, Mision), ya calculados por la API. La UI solo los muestra.

// //todo_#156: lista real de misiones (GET /v1/missions)
export type MissionState = 'running' | 'valuation' | 'closed' | 'cancelled'
export type MissionPhase = 'search' | 'filter' | 'negotiation' | 'valuation'
export interface MissionRow {
  id: string
  title: string
  state: MissionState
  phase: MissionPhase
  offers: number
  finalists: number
  launchedAt: string
}
export const missionList: MissionRow[] = [
  { id: 'M-0142', title: 'Rodamiento 6204-2RS · 5.000 ud', state: 'running', phase: 'negotiation', offers: 23, finalists: 0, launchedAt: '2026-11-09T12:00:00+01:00' },
  { id: 'M-0141', title: 'Cable apantallado · 3.000 m', state: 'valuation', phase: 'valuation', offers: 31, finalists: 3, launchedAt: '2026-11-08T09:30:00+01:00' },
  { id: 'M-0139', title: 'Junta tórica NBR · 20.000 ud', state: 'closed', phase: 'valuation', offers: 18, finalists: 2, launchedAt: '2026-11-04T16:10:00+01:00' },
  { id: 'M-0137', title: 'Válvula de bola DN25 · 800 ud', state: 'cancelled', phase: 'filter', offers: 12, finalists: 0, launchedAt: '2026-11-02T11:45:00+01:00' },
]

// Matriz de ofertas (pendiente de GET /v1/missions/{id}/offers, #157)
export interface OfferRow {
  id: string
  seller: string
  platform: 'p1' | 'p2'
  priceMinor: number
  /** Diferencia con la mediana, en %. */
  deltaPct: number
  priceBand: PriceBand
  confidence: { band: ConfidenceBand; score: number }
  verdict: FinancialVerdict
  signature: SignatureStatus
  status: { kind: 'awaiting_approval' | 'negotiating' | 'aborted' | 'gate_low_confidence' | 'filtered_implausible'; round?: number }
  landedMinor: number
  /** Ruta sin prefijo de idioma. */
  href: string
}
