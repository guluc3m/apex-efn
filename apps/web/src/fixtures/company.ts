// //todo_#167: reglas efectivas y su historial vendrán de GET config (config_version) y no se calculan aquí
export type RuleOrigin = 'template' | 'proposed' | 'policy' | 'category' | 'required'
export interface Rule {
  key: string
  group: 'sanity' | 'seller' | 'signing' | 'negotiation'
  /** null = sin definir (salvo que haya `valueKey`). `valueKey` es un valor textual traducible. */
  value: string | null
  valueKey?: 'goGate' | 'medium'
  origin: RuleOrigin
}

export const rulesConfig = {
  version: 'v3',
  scopes: ['all', 'bearings', 'valves'],
  rules: [
    { key: 'sanity.z_ok', group: 'sanity', value: '3,5', origin: 'template' },
    { key: 'sanity.z_gate', group: 'sanity', value: '6,0 → 5,0', origin: 'proposed' },
    { key: 'sanity.on_insufficient_reference', group: 'sanity', value: null, valueKey: 'goGate', origin: 'template' },
    { key: 'sanity.floor_per_unit', group: 'sanity', value: null, origin: 'category' },
    { key: 'seller.min_accepted_band', group: 'seller', value: null, valueKey: 'medium', origin: 'policy' },
    { key: 'seller.hard_block_below', group: 'seller', value: '20', origin: 'template' },
    { key: 'approval.dual_control_above', group: 'signing', value: null, origin: 'required' },
    { key: 'signing.high_value_reauth_above', group: 'signing', value: null, origin: 'required' },
    { key: 'signing.session_minutes', group: 'signing', value: '15 min', origin: 'template' },
    { key: 'neg.max_rounds', group: 'negotiation', value: '6', origin: 'template' },
    { key: 'neg.max_discount', group: 'negotiation', value: '8 %', origin: 'policy' },
  ] satisfies Rule[],
  proposal: { key: 'sanity.z_gate', change: '6,0 → 5,0', impactCount: 2, reason: 'Demasiados precios dudosos en cable entran como normales.' },
  history: [
    { version: 'v3', date: '02/11', by: 'finance', text: 'Descuento máximo de Rodamientos a 8 %' },
    { version: 'v2', date: '20/10', by: 'owner', text: 'Banda mínima sin gate: media' },
    { version: 'v1', date: '14/10', by: 'template', text: 'Valores iniciales' },
  ],
}

// //todo_#166: eventos y estado de cadena vendrán de GET /v1/audit y /v1/audit/verify
export const auditData = {
  chain: 'intact',
  events: 18204,
  lastVerified: 'Hoy 12:00',
  anchor: 'e41d…77a0',
  rows: [
    { id: 'e5', time: '12:08:31', actor: 'negotiator', text: 'Mensaje enviado a Vendedor H (aprobado por Responsable)', hash: 'a41f…9c02' },
    { id: 'e4', time: '12:05:30', actor: 'sanity', text: 'Vendedor F descartado · precio implausible', hash: '0b7e…13d9' },
    { id: 'e3', time: '10:42:07', actor: 'human', text: 'Primera firma · Motor trifásico 4 kW', hash: 'c90a…5e21' },
    { id: 'e2', time: '10:30:12', actor: 'human', text: 'Sesión de firma abierta con passkey', hash: '77d2…a0f4' },
    { id: 'e1', time: '09:00:00', actor: 'fx', text: 'Tipos BCE del 07/11 cargados', hash: '18ce…fe60' },
  ],
}
export type AuditRow = (typeof auditData.rows)[number]

// //todo_#147: roles con acceso a auditoría según la sesión
export const auditRoles = ['admin', 'owner']
