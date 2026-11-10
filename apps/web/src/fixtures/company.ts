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

export const auditRoles = ['admin', 'owner']
