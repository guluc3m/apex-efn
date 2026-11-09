import type { ConfidenceBand, FinancialVerdict, PriceBand, SignatureStatus } from '@apex/ui'

// Datos del lienzo (Peticion, Mision), ya calculados por la API. La UI solo los muestra.

// //todo_#178: lista real de misiones (GET /v1/missions)
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

// //todo_#155: estado real del snapshot financiero activo
export const financialSnapshotActive = true

// //todo_#172: petición interpretada por el IntakeAgent (POST /v1/sourcing-requests)
export const sourcingRequest = {
  text: 'Necesito 5.000 rodamientos 6204-2RS con doble sellado de goma, entrega en la nave de Valencia antes del 15 de diciembre. Pago a 60 días si puede ser.',
  fields: {
    product: 'Rodamiento rígido de bolas 6204-2RS',
    quantity: '5.000 ud',
    destination: 'Valencia, España',
    deadline: '15/12/2026',
    spec: '20×47×14 mm · doble sello de goma (2RS)',
  },
  platforms: [
    { id: 'p1', state: 'on' },
    { id: 'p2', state: 'expired' },
    { id: 'p3', state: 'disabled' },
  ],
  envelope: { amountMinor: 1840000, currency: 'EUR' },
} as const

// //todo_#156: misión en curso (GET /v1/missions/{id} + SSE /events)
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
const neg = (id: string) => `/misiones/M-0142/negociaciones/${id}`
const offers: OfferRow[] = [
  { id: 'o-h', seller: 'Vendedor H', platform: 'p2', priceMinor: 181, deltaPct: 1, priceBand: 'normal', confidence: { band: 'medium', score: 63 }, verdict: 'within_budget', signature: 'pending', status: { kind: 'awaiting_approval' }, landedMinor: 1039000, href: neg('n-h') },
  { id: 'o-k', seller: 'Vendedor K', platform: 'p2', priceMinor: 164, deltaPct: -9, priceBand: 'normal', confidence: { band: 'low', score: 38 }, verdict: 'within_budget', signature: 'pending', status: { kind: 'gate_low_confidence' }, landedMinor: 961000, href: '/decisiones/o-k' },
  { id: 'o-a', seller: 'Vendedor A', platform: 'p1', priceMinor: 172, deltaPct: -4, priceBand: 'normal', confidence: { band: 'high', score: 86 }, verdict: 'within_budget', signature: 'pending', status: { kind: 'negotiating', round: 3 }, landedMinor: 984200, href: neg('n-a') },
  { id: 'o-j', seller: 'Vendedor J', platform: 'p1', priceMinor: 195, deltaPct: 8, priceBand: 'normal', confidence: { band: 'high', score: 79 }, verdict: 'stretch', signature: 'pending', status: { kind: 'aborted', round: 1 }, landedMinor: 1102000, href: neg('n-j') },
  { id: 'o-f', seller: 'Vendedor F', platform: 'p1', priceMinor: 22, deltaPct: -88, priceBand: 'implausible', confidence: { band: 'insufficient_data', score: 0 }, verdict: 'within_budget', signature: 'pending', status: { kind: 'filtered_implausible' }, landedMinor: 142000, href: '/decisiones/o-f' },
]

export const mission = {
  id: 'M-0142',
  title: 'Rodamiento 6204-2RS · 5.000 ud',
  launchedMinutesAgo: 6,
  medianMinor: 180,
  total: 23,
  phases: [
    { id: 'search', state: 'done', values: { n: 23, p: 2 } },
    { id: 'filter', state: 'done', values: { pass: 9, out: 14 } },
    { id: 'negotiation', state: 'running', values: { n: 2, total: 5 } },
    { id: 'valuation', state: 'pending', values: {} },
  ],
  offers,
  funnel: [
    { id: 'found', n: 23 },
    { id: 'passed', n: 9 },
    { id: 'negotiated', n: 5 },
    { id: 'finalists', n: 3 },
  ],
  activity: [
    { time: '12:06:41', kind: 'reply', values: { seller: 'Vendedor A' } },
    { time: '12:06:12', kind: 'draft', values: { seller: 'Vendedor H' }, href: neg('n-h') },
    { time: '12:05:30', kind: 'discarded', values: { seller: 'Vendedor F', pct: 88 } },
    { time: '12:04:55', kind: 'gate', values: { seller: 'Vendedor K', score: 38 } },
    { time: '12:03:02', kind: 'offers', values: { platform: 'Plataforma 2', n: 9 } },
    { time: '12:02:47', kind: 'offers', values: { platform: 'Plataforma 1', n: 14 } },
  ],
  workingOn: 2,
} as const
