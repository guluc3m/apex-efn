import type { Drafts } from '@/components/onboarding/schemas'

const categorias = [
  { id: 'bearings', label: 'Rodamientos' },
  { id: 'valves', label: 'Válvulas' },
]

// Empty drafts: the server restores company and sector (GET /v1/onboarding/sessions). Amounts and percentages have no default.
export const initialDrafts: Drafts = {
  empresa: { razonSocial: '', cif: '', pais: 'es', aduana: 'eori', direccion: '', facturacionIgual: true },
  sector: { cnae: '', frecuencia: 'monthly', compras: '', estacionalidad: '' },
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
