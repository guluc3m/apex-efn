// //todo_#148: sustituir por GET /v1/negotiations/{id} (transcripción, borrador, límites) cuando exista el BFF
import type { ConfidenceBand, PriceBand } from '@apex/ui'

export type NegotiationState = 'active' | 'human' | 'aborted' | 'reopened'

/** Trozo de mensaje: texto (con idioma si no es el de la interfaz) o precio detectado, ya formateado y con su banda. */
export type MessagePart = { text: string; lang?: string } | { price: string; band: PriceBand }

export interface TranscriptMessage {
  id: string
  role: 'agent' | 'seller' | 'human'
  initials: string
  author: string
  platform: string
  time: string
  parts: MessagePart[]
  /** Traducción hecha por el backend. */
  translation?: { text: string; lang: string }
}

export interface LadderPoint {
  round: string
  /** Solo para dibujar; el importe visible es `label`. */
  value: number
  label: string
  /** Borrador sin enviar. */
  draft?: boolean
}

export interface NegotiationFixture {
  id: string
  missionCode: string
  seller: string
  platform: string
  state: NegotiationState
  round: number
  maxRounds: number
  messages: TranscriptMessage[]
  /** Separador «Reabierta por X a las 12:40»; solo si la fixture lo trae. */
  reopened?: { by: string; time: string }
  draft: { initials: string; text: string; guardrails: string[]; note: string }
  offer: { current: string; initial: string; delta: string; target: string }
  confidence: { band: ConfidenceBand; score: number; signals: { k: string; v: string }[] }
  price: { band: PriceBand; signals: { k: string; v: string }[] }
  limits: { k: string; v: string }[]
  ladder: { points: LadderPoint[]; target: { value: number; label: string }; max: { value: number; label: string } }
  escalation: { seller: string; reason: string; dealId: string }
  screenshots: number
  /** Motivo si la oferta ha caducado y no se puede reabrir. */
  reopenBlocked?: string
}

const seller = { initials: 'VH', author: 'Vendedor H', platform: 'Plataforma 2' } as const
const agent = { initials: 'AG', author: 'Agente', platform: 'Plataforma 2' } as const

export function getNegotiation(state: NegotiationState): NegotiationFixture {
  return {
    id: 'neg_01',
    missionCode: 'M-0142',
    seller: 'Vendedor H',
    platform: 'Plataforma 2',
    state,
    round: 2,
    maxRounds: 6,
    messages: [
      { id: 'm1', role: 'agent', ...agent, time: '12:03', parts: [{ text: 'Buenos días. Buscamos 5.000 ud de 6204-2RS para Valencia antes del 15/12, con compras recurrentes. ¿Qué escalado de precio aplicáis por volumen?' }] },
      {
        id: 'm2', role: 'seller', ...seller, time: '12:04',
        parts: [{ text: '5.000 ud a ' }, { price: '1,81 €/ud', band: 'normal' }, { text: '. A partir de 10.000 bajamos a ' }, { price: '1,70 €/ud', band: 'normal' }, { text: '.' }],
        translation: { text: '5.000 uds a 1,81 €/ud. A partir de 10.000, bajamos a 1,70 €/ud.', lang: 'es' },
      },
      { id: 'm3', role: 'agent', ...agent, time: '12:05', parts: [{ text: 'No podemos pasar de 5.000 en este pedido. Con pedidos mensuales, ¿podéis mantener ' }, { price: '1,70 €/ud', band: 'normal' }, { text: ' en 5.000?' }] },
      {
        id: 'm4', role: 'seller', ...seller, time: '12:06',
        parts: [{ price: '1,76 €/ud', band: 'normal' }, { text: ' si confirmáis hoy. ' }, { text: '也可以人民币报价。', lang: 'zh-Hans' }],
        translation: { text: '1,76 €/ud si confirmáis hoy. También podemos cotizar en yuanes.', lang: 'es' },
      },
      ...(state === 'human'
        ? [{ id: 'm5', role: 'human' as const, initials: 'MR', author: 'Marta Ruiz', platform: 'Plataforma 2', time: '12:09', parts: [{ text: 'Os confirmo el pedido de 5.000 si mantenéis el plazo del 15/12.' }] }]
        : []),
    ],
    reopened: state === 'reopened' ? { by: 'Responsable', time: '12:40' } : undefined,
    draft: {
      initials: 'AG',
      text: 'Gracias. Podemos confirmar esta semana a 1,72 €/ud con entrega antes del 15/12. ¿Lo dejáis por escrito con las condiciones de pago a 60 días?',
      guardrails: ['Descuento pedido 5 %, máximo 8 %', 'Volumen sin cambios', 'Sin prepago ni penalizaciones'],
      note: '"Si confirmáis hoy": el agente no acepta compromisos; te avisará antes de cerrar.',
    },
    offer: { current: '1,76 €', initial: '1,81 €', delta: '−3 %', target: '1,70 €' },
    confidence: {
      band: 'medium',
      score: 63,
      signals: [
        { k: 'Antigüedad', v: '900 días' },
        { k: 'Ventas', v: '640 ventas · 21 % repetición' },
        { k: 'Catálogo', v: '110 productos · ficha 74 %' },
        { k: 'Reseñas', v: '4,4 de 88 · 62 % verificadas' },
        { k: 'Garantía institucional', v: 'KYC · sin escrow · disputas 1,9 %' },
        { k: 'Calidad del dato', v: '80 %' },
      ],
    },
    price: { band: 'normal', signals: [{ k: 'Oferta actual', v: '1,76 €/ud' }, { k: 'Objetivo', v: '1,70 €/ud' }, { k: 'Explicación', v: 'Dentro de la banda normal' }] },
    limits: [
      { k: 'Rondas', v: '2 de 6' },
      { k: 'Tokens de la conversación', v: '3.100 de 12.000' },
      { k: 'Mensajes en la última hora', v: '3 de 20' },
      { k: 'Contrapartidas permitidas', v: 'Mayor volumen' },
    ],
    ladder: {
      points: [
        { round: '1', value: 1.81, label: '1,81 €' },
        { round: '2', value: 1.76, label: '1,76 €' },
        { round: '3', value: 1.72, label: '1,72 €', draft: true },
      ],
      target: { value: 1.7, label: '1,70 €' },
      max: { value: 1.67, label: '1,67 €' },
    },
    escalation: { seller: 'Vendedor K', reason: 'Vendedor J pide pagar por transferencia fuera de la plataforma. El agente se ha detenido.', dealId: 'deal_k' },
    screenshots: 14,
  }
}
