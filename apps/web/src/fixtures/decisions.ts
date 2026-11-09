import type { ConfidenceBand, FinancialVerdict, PriceBand } from '@apex/ui'

// Datos de maqueta del lienzo (Estilo). Todo llega ya calculado: la UI no deriva nada.
// //todo_#148: sustituir por GET /v1/gate/queue, GET /v1/dashboard/deals y GET /v1/missions/{id}/recommendation

export type ActionKey = 'follow' | 'renegotiate' | 'takeover' | 'hold' | 'discard' | 'unblock' | 'override_discard' | 'sign2'
export type Profile = 'comprador' | 'cfo'

export interface DealSignals {
  ageDays: number
  sales: number
  repeatPct: number
  products: number
  listingPct: number
  rating: number
  reviews: number
  verifiedPct: number
  kyc: boolean
  escrow: boolean
  disputesPct: number
}

export interface Deal {
  id: string
  tenant?: boolean
  title: string
  /** Clave en decisions.cause.* */
  cause: string
  sla?: string
  seller?: string
  platform?: string
  unitMinor?: number
  initialMinor?: number
  /** El servidor indica si el precio ya se ha negociado. */
  negotiated?: boolean
  qty?: number
  subtotalMinor?: number
  totalMinor?: number
  deltaPct?: number
  score?: number
  conf?: ConfidenceBand
  band?: PriceBand
  verdict?: FinancialVerdict
  /** Clave en decisions.sig.* */
  sig?: { status: 'signed' | 'pending'; key: 'pending' | 'pending12' | 'none' }
  expiresDays?: number
  signals?: DealSignals
  /** Claves en decisions.sanity.* y decisions.risk.* */
  sanity?: string
  risk?: string[]
  lines?: { key: string; minor: number }[]
  /** Contribución ya ponderada y formateada por el servidor, y ancho de barra. */
  contrib?: Record<Profile, { key: string; value: string; pct: number }[]>
  transcript?: { who: 'agent' | 'seller'; text: string }[]
  /** `reason` es una clave de decisions.reason.* (la API devolverá el texto). */
  actions: { key: ActionKey; reason?: string; passkey?: boolean }[]
}

const lines = (m: number[]) => ['shipping', 'insurance', 'duties', 'capital', 'fees', 'fx'].map((key, i) => ({ key, minor: m[i]! }))

const talk: NonNullable<Deal['transcript']> = [
  { who: 'agent', text: 'Saludo y contexto de la compra.' },
  { who: 'seller', text: 'Precio de lista y disponibilidad.' },
  { who: 'agent', text: 'Pregunta por escalones de volumen.' },
  { who: 'seller', text: 'Contraoferta con descuento.' },
  { who: 'agent', text: 'Resumen escrito de las condiciones.' },
]
const HIGH: DealSignals = { ageDays: 2900, sales: 4210, repeatPct: 38, products: 320, listingPct: 92, rating: 4.7, reviews: 610, verifiedPct: 81, kyc: true, escrow: true, disputesPct: 0.6 }
const MED: DealSignals = { ageDays: 900, sales: 640, repeatPct: 21, products: 110, listingPct: 74, rating: 4.4, reviews: 88, verifiedPct: 62, kyc: true, escrow: false, disputesPct: 1.9 }
const LOW: DealSignals = { ageDays: 140, sales: 32, repeatPct: 4, products: 12, listingPct: 40, rating: 4.9, reviews: 41, verifiedPct: 9, kyc: false, escrow: false, disputesPct: 5.2 }
const pend = { status: 'pending', key: 'pending' } as const

export const deals: Deal[] = [
  { id: 'c', title: 'Cable apantallado · 3.000 m', cause: 'atypicalPrice', sla: '02:10', seller: 'Vendedor C', platform: 'Plataforma 1', unitMinor: 900, initialMinor: 900, qty: 3000, subtotalMinor: 2700000, totalMinor: 2826000, score: 71, conf: 'medium', band: 'atypical', verdict: 'within_budget', sig: pend, expiresDays: 3, signals: MED, sanity: 'atypical', risk: ['below60'], lines: lines([90000, 18000, 0, 12000, 0, 6000]), actions: [{ key: 'unblock' }, { key: 'discard' }] },
  { id: 'b', title: 'Válvula de bola DN25 · 800 ud', cause: 'lowConfidence', sla: '05:20', seller: 'Vendedor B', platform: 'Plataforma 2', negotiated: true, unitMinor: 1240, initialMinor: 1490, qty: 800, subtotalMinor: 992000, totalMinor: 1203200, deltaPct: 17, score: 38, conf: 'low', band: 'normal', verdict: 'within_budget', sig: pend, expiresDays: 2, signals: LOW, sanity: 'normal', risk: ['burst'], lines: lines([41000, 9920, 148380, 6100, 3000, 2800]), contrib: { comprador: [{ key: 'landed', value: '0.11', pct: 31 }, { key: 'lead', value: '0.18', pct: 51 }, { key: 'confidence', value: '0.06', pct: 17 }, { key: 'fit', value: '0.04', pct: 11 }, { key: 'margin', value: '0.03', pct: 9 }, { key: 'spec', value: '0.07', pct: 20 }, { key: 'compliance', value: '0.05', pct: 14 }, { key: 'gain', value: '0.03', pct: 9 }], cfo: [{ key: 'landed', value: '0.19', pct: 54 }, { key: 'lead', value: '0.03', pct: 9 }, { key: 'confidence', value: '0.05', pct: 14 }, { key: 'fit', value: '0.15', pct: 43 }, { key: 'margin', value: '0.03', pct: 9 }, { key: 'spec', value: '0.03', pct: 9 }, { key: 'compliance', value: '0.03', pct: 9 }, { key: 'gain', value: '0.03', pct: 9 }] }, transcript: talk, actions: [{ key: 'follow', reason: 'blockLow' }, { key: 'unblock' }, { key: 'renegotiate' }, { key: 'hold' }, { key: 'discard' }] },
  { id: 'e', title: 'Motor trifásico 4 kW · 60 ud', cause: 'secondSignature', sla: '08:30', seller: 'Vendedor E', platform: 'Plataforma 1', negotiated: true, unitMinor: 21500, initialMinor: 24800, qty: 60, subtotalMinor: 1290000, totalMinor: 1714000, deltaPct: 13, score: 91, conf: 'high', band: 'normal', verdict: 'stretch', sig: { status: 'pending', key: 'pending12' }, expiresDays: 5, signals: HIGH, sanity: 'normal', risk: [], lines: lines([62000, 12900, 333300, 8400, 3900, 3500]), contrib: { comprador: [{ key: 'landed', value: '0.11', pct: 31 }, { key: 'lead', value: '0.29', pct: 83 }, { key: 'confidence', value: '0.19', pct: 54 }, { key: 'fit', value: '0.02', pct: 6 }, { key: 'margin', value: '0.03', pct: 9 }, { key: 'spec', value: '0.09', pct: 26 }, { key: 'compliance', value: '0.09', pct: 26 }, { key: 'gain', value: '0.03', pct: 9 }], cfo: [{ key: 'landed', value: '0.18', pct: 51 }, { key: 'lead', value: '0.05', pct: 14 }, { key: 'confidence', value: '0.19', pct: 54 }, { key: 'fit', value: '0.16', pct: 46 }, { key: 'margin', value: '0.03', pct: 9 }, { key: 'spec', value: '0.05', pct: 14 }, { key: 'compliance', value: '0.05', pct: 14 }, { key: 'gain', value: '0.03', pct: 9 }] }, transcript: talk, actions: [{ key: 'sign2' }] },
  { id: 'd', title: 'Sensor PT100 · 1.200 ud', cause: 'escalatedDiscard', sla: '09:15', seller: 'Vendedor D', platform: 'Plataforma 2', unitMinor: 240, initialMinor: 240, qty: 1200, subtotalMinor: 288000, totalMinor: 328800, score: 22, conf: 'untrusted', band: 'implausible', verdict: 'within_budget', sig: { status: 'pending', key: 'none' }, expiresDays: 1, signals: LOW, sanity: 'escalated', risk: ['escalated'], lines: lines([32120, 2880, 0, 3100, 0, 2700]), actions: [{ key: 'override_discard', passkey: true }] },
  { id: 't', tenant: true, title: 'Snapshot financiero caducado', cause: 'staleSnapshot', sla: '11:45', actions: [] },
  { id: 'a', title: 'Rodamiento 6204-2RS · 5.000 ud', cause: 'ready', seller: 'Vendedor A', platform: 'Plataforma 1', negotiated: true, unitMinor: 172, initialMinor: 181, qty: 5000, subtotalMinor: 860000, totalMinor: 984200, deltaPct: 5, score: 86, conf: 'high', band: 'normal', verdict: 'within_budget', sig: pend, expiresDays: 4, signals: HIGH, sanity: 'normal', risk: [], lines: lines([27200, 3700, 84700, 4200, 1800, 2600]), contrib: { comprador: [{ key: 'landed', value: '0.12', pct: 34 }, { key: 'lead', value: '0.28', pct: 80 }, { key: 'confidence', value: '0.18', pct: 51 }, { key: 'fit', value: '0.05', pct: 14 }, { key: 'margin', value: '0.03', pct: 9 }, { key: 'spec', value: '0.09', pct: 26 }, { key: 'compliance', value: '0.09', pct: 26 }, { key: 'gain', value: '0.02', pct: 6 }], cfo: [{ key: 'landed', value: '0.20', pct: 57 }, { key: 'lead', value: '0.05', pct: 14 }, { key: 'confidence', value: '0.18', pct: 51 }, { key: 'fit', value: '0.32', pct: 91 }, { key: 'margin', value: '0.03', pct: 9 }, { key: 'spec', value: '0.04', pct: 11 }, { key: 'compliance', value: '0.04', pct: 11 }, { key: 'gain', value: '0.00', pct: 0 }] }, transcript: talk, actions: [{ key: 'follow', reason: 'staleFinancials' }, { key: 'renegotiate' }, { key: 'takeover' }, { key: 'hold' }, { key: 'discard' }] },
  { id: 'g', title: 'Compresor de tornillo · 12 ud', cause: 'highAmount', seller: 'Vendedor G', platform: 'Plataforma 2', negotiated: true, unitMinor: 412000, initialMinor: 468000, qty: 12, subtotalMinor: 4944000, totalMinor: 6404440, deltaPct: 12, score: 79, conf: 'high', band: 'normal', verdict: 'stretch', sig: pend, expiresDays: 6, signals: HIGH, sanity: 'normal', risk: [], lines: lines([190000, 49440, 1130000, 52000, 21000, 18000]), contrib: { comprador: [{ key: 'landed', value: '0.08', pct: 23 }, { key: 'lead', value: '0.18', pct: 51 }, { key: 'confidence', value: '0.14', pct: 40 }, { key: 'fit', value: '0.03', pct: 9 }, { key: 'margin', value: '0.04', pct: 11 }, { key: 'spec', value: '0.08', pct: 23 }, { key: 'compliance', value: '0.08', pct: 23 }, { key: 'gain', value: '0.03', pct: 9 }], cfo: [{ key: 'landed', value: '0.14', pct: 40 }, { key: 'lead', value: '0.03', pct: 9 }, { key: 'confidence', value: '0.14', pct: 40 }, { key: 'fit', value: '0.18', pct: 51 }, { key: 'margin', value: '0.04', pct: 11 }, { key: 'spec', value: '0.04', pct: 11 }, { key: 'compliance', value: '0.04', pct: 11 }, { key: 'gain', value: '0.03', pct: 9 }] }, transcript: talk, actions: [{ key: 'follow', reason: 'staleFinancials', passkey: true }, { key: 'renegotiate' }, { key: 'takeover' }, { key: 'hold' }, { key: 'discard' }] },
]

/** Orden de cada vista; en «tratos» lo decide el servidor según el perfil. */
export const views = { cola: ['c', 'b', 'e', 'd', 't'], tratos: { comprador: ['e', 'a', 'g', 'b'], cfo: ['a', 'g', 'e', 'b'] } } as const
export const rankScore: Record<Profile, Record<string, number>> = {
  comprador: { e: 0.72, a: 0.66, g: 0.55, b: 0.41 },
  cfo: { a: 0.7, g: 0.58, e: 0.52, b: 0.44 },
}
export const discardReasons = ['price_too_high', 'seller_not_trusted', 'spec_mismatch', 'lead_time', 'out_of_budget', 'duplicate', 'other']

export const kpis = [
  { key: 'pending', value: '5', spark: [9, 8, 8, 7, 6, 6, 5] },
  { key: 'signed', value: '14', spark: [2, 3, 3, 5, 8, 11, 14] },
  { key: 'sla', value: '02:10', spark: [6, 5, 5, 4, 3, 3, 2] },
]
export const savings = {
  totalMinor: 1284000,
  weeks: [296300, 444500, 370400, 765500, 691400, 1086500, 1284000].map((minor, i) => ({ week: i + 1, minor })),
}
