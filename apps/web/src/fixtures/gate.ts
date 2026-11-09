// //todo_#163: sustituir por GET /v1/gate/queue (SLA, porcentaje y orden ya calculados por la API)
export type GateCause = 'negotiator' | 'price' | 'confidence' | 'second_signature' | 'high_amount' | 'discard' | 'company'
export type GateAction = 'unblock' | 'override_discard'

export interface GateItem {
  id: string
  dealId: string
  cause: GateCause
  title: string
  /** Vendedor o contexto, ya redactado por la API. */
  sub?: string
  /** Aviso extra bajo el título. */
  flag?: 'no_reference' | 'new_seller'
  /** Importe ya formateado. */
  amount?: string
  /** Importe en unidades menores, solo para ordenar. */
  amountMinor?: number
  /** Tiempo restante `hh:mm`. */
  sla: string
  /** Minutos restantes: orden de urgencia. */
  slaMinutes: number
  /** Urgencia: menos de 1 h o menos de 3 h. */
  slaTone?: 'bad' | 'warn'
  /** Porcentaje de SLA que queda (la barra se vacía), calculado por la API. */
  slaPct?: number
  /** Vence hoy. */
  dueToday: boolean
  assignee: 'owner' | 'finance' | 'none'
  /** Asignado al usuario actual. */
  mine: boolean
  reminderAt?: string
  actions: GateAction[]
}

const U: GateAction[] = ['unblock']

// //todo_#163: sustituir por GET /v1/gate/queue
export const gateQueue: GateItem[] = [
  { id: 'g1', dealId: 'd-k', cause: 'negotiator', title: 'Vendedor K pide pago fuera de la plataforma', sla: '00:40', slaMinutes: 40, slaTone: 'bad', slaPct: 3, dueToday: true, assignee: 'owner', mine: true, reminderAt: '11:30', actions: U },
  { id: 'g2', dealId: 'd-c', cause: 'price', title: 'Cable apantallado · 3.000 m', sub: 'Vendedor C', amount: '28.260,00 €', amountMinor: 2826000, sla: '02:10', slaMinutes: 130, slaTone: 'warn', slaPct: 9, dueToday: true, assignee: 'owner', mine: true, reminderAt: '10:00', actions: U },
  { id: 'g3', dealId: 'd-m', cause: 'price', title: 'Junta tórica NBR · 20.000 ud', sub: 'Vendedor M', flag: 'no_reference', amount: '1.940,00 €', amountMinor: 194000, sla: '14:30', slaMinutes: 870, dueToday: true, assignee: 'none', mine: false, actions: U },
  { id: 'g4', dealId: 'd-l', cause: 'price', title: 'Rodamiento 6204-2RS · 5.000 ud', sub: 'Vendedor L', amount: '20.180,00 €', amountMinor: 2018000, sla: '21:05', slaMinutes: 1265, dueToday: false, assignee: 'owner', mine: true, actions: U },
  { id: 'g5', dealId: 'd-b', cause: 'confidence', title: 'Válvula de bola DN25 · 800 ud', sub: 'Vendedor B', amount: '12.032,00 €', amountMinor: 1203200, sla: '05:20', slaMinutes: 320, dueToday: true, assignee: 'owner', mine: true, actions: U },
  { id: 'g6', dealId: 'd-k2', cause: 'confidence', title: 'Rodamiento 6204-2RS · 5.000 ud', sub: 'Vendedor K', flag: 'new_seller', amount: '9.610,00 €', amountMinor: 961000, sla: '23:40', slaMinutes: 1420, dueToday: false, assignee: 'none', mine: false, actions: U },
  { id: 'g7', dealId: 'd-mt', cause: 'second_signature', title: 'Motor trifásico 4 kW · 60 ud', sub: '1 de 2 firmas', amount: '17.140,00 €', amountMinor: 1714000, sla: '08:30', slaMinutes: 510, dueToday: true, assignee: 'finance', mine: false, actions: U },
  { id: 'g8', dealId: 'd-g', cause: 'high_amount', title: 'Compresor de tornillo · 12 ud', sub: 'Vendedor G', amount: '64.044,40 €', amountMinor: 6404440, sla: '06:20', slaMinutes: 380, dueToday: true, assignee: 'finance', mine: false, actions: U },
  { id: 'g9', dealId: 'd-s', cause: 'discard', title: 'Sensor PT100 · 1.200 ud', sub: 'descartado por regla de escalada', amount: '3.288,00 €', amountMinor: 328800, sla: '09:15', slaMinutes: 555, dueToday: true, assignee: 'finance', mine: false, actions: ['override_discard'] },
  { id: 'g10', dealId: 'd-fin', cause: 'company', title: 'Snapshot financiero caducado: bloquea compras directas', sla: '11:45', slaMinutes: 705, dueToday: true, assignee: 'finance', mine: false, actions: U },
]
