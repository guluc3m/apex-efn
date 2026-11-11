import type { Drafts } from '@/components/onboarding/schemas'

// Empty drafts: the server restores company and sector (GET /v1/onboarding/sessions). Amounts and percentages have no default.
export const initialDrafts: Drafts = {
  empresa: { razonSocial: '', cif: '', pais: 'es', aduana: 'eori', direccion: '', facturacionIgual: true },
  sector: { cnae: '', frecuencia: 'monthly', compras: '', estacionalidad: '' },
  presupuesto: {
    divisa: 'EUR',
    pago: 'd60',
    colchon: '15',
    categorias: [],
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
    categorias: [],
    agresividad: 'balanced',
    tono: 'formal',
    idioma: 'seller',
    contrapartidas: ['volume'],
  },
}

export const certifications = ['CE', 'ISO 9001', 'REACH', 'FCC']

