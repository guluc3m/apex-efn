import type { Drafts, StepId } from '@/components/onboarding/schemas'

// //todo_#152: estado de cada paso, borrador guardado y mensajes del asistente vendrán de /v1/onboarding
export const stepStatus: Record<StepId, { kind: 'done' | 'warnings' | 'pending' | 'none'; count?: number }> = {
  empresa: { kind: 'done' },
  sector: { kind: 'done' },
  cuentas: { kind: 'warnings', count: 1 },
  presupuesto: { kind: 'none' },
  politica: { kind: 'pending', count: 2 },
  negociacion: { kind: 'pending', count: 4 },
  finanzas: { kind: 'none' },
}

const categorias = [
  { id: 'bearings', label: 'Rodamientos' },
  { id: 'valves', label: 'Válvulas' },
]

// //todo_#152: borrador inicial desde el servidor. Importes y porcentajes sin valor por defecto en política y negociación.
export const initialDrafts: Drafts = {
  empresa: {
    razonSocial: 'Industrias Ejemplo, S.L.',
    cif: 'B00000000',
    pais: 'es',
    aduana: 'eori',
    direccion: 'Polígono Industrial, nave 4 · 46000 Valencia',
    facturacionIgual: true,
  },
  sector: {
    cnae: '2829 · Fabricación de maquinaria',
    frecuencia: 'monthly',
    compras: 'Rodamientos, válvulas, cable apantallado y sensores para mantenimiento de línea.',
    estacionalidad: 'Picos en marzo y septiembre (paradas de mantenimiento)',
  },
  presupuesto: {
    divisa: 'EUR',
    pago: 'd60',
    colchon: '15',
    categorias: [
      { id: 'bearings', label: 'Rodamientos', envelope: '25.000,00 €', maximo: '12.000,00 €' },
      { id: 'valves', label: 'Válvulas', envelope: '18.000,00 €', maximo: '10.000,00 €' },
      { id: 'cables', label: 'Cable y sensores', envelope: '9.000,00 €', maximo: '5.000,00 €' },
    ],
  },
  politica: {
    aprobacion: '',
    doble: '',
    confianza: 'medium',
    plazo: 'late10',
    certificaciones: ['CE', 'ISO 9001'],
    paisesExcluidos: '',
    vetados: '',
  },
  negociacion: {
    categorias: categorias.map((c) => ({ ...c, objetivo: '', maximo: '' })),
    agresividad: 'balanced',
    tono: 'formal',
    idioma: 'seller',
    contrapartidas: ['volume'],
  },
}

export const certifications = ['CE', 'ISO 9001', 'REACH', 'FCC']

export interface Platform {
  id: string
  name: string
  connection: 'oauth' | 'password'
  state: 'connected' | 'expired' | 'none'
}

// //todo_#154: cuentas conectadas reales (solo identificador y estado, nunca credenciales)
export const platforms: Platform[] = [
  { id: 'p1', name: 'Plataforma 1', connection: 'oauth', state: 'connected' },
  { id: 'p2', name: 'Plataforma 2', connection: 'password', state: 'expired' },
  { id: 'p3', name: 'Plataforma 3', connection: 'password', state: 'none' },
]

// //todo_#152: conversación y propuesta del IntakeAgent
export const assistantMessages = [
  { id: 'm1', role: 'agent', text: '¿Qué compráis con más frecuencia y cada cuánto?' },
  { id: 'm2', role: 'human', text: 'Rodamientos y válvulas cada mes. Paramos línea en marzo y septiembre.' },
] as const

// //todo_#152: umbrales efectivos de /v1/config (solo lectura). `null` = sin definir en el tenant.
export const effectiveThresholds: { key: 'referenceWeights' | 'approval' | 'dual'; value: string | null }[] = [
  { key: 'referenceWeights', value: '50 / 30 / 20 %' },
  { key: 'approval', value: null },
  { key: 'dual', value: null },
]
