// //todo_#165: sustituir por la bandeja de aprobaciones real (doble control, documentos y seguimiento) cuando exista el contrato (issue #302)
export type ApprovalStatus = 'sign' | 'progress' | 'closed'
export const APPROVAL_TABS: readonly ApprovalStatus[] = ['sign', 'progress', 'closed']

export interface ApprovalSignature {
  slot: 'first' | 'second'
  who: string
  when: string
  signed: boolean
}

export interface ApprovalDocument {
  kind: 'rfq' | 'po' | 'certificate'
  hash?: string
  available: boolean
}

export interface ApprovalFixture {
  id: string
  status: ApprovalStatus
  note: 'secondMissing' | 'highAmount' | 'inTransit'
  title: string
  amount: string
  seller: string
  signatures: ApprovalSignature[]
  documents: ApprovalDocument[]
  tracking: { when: string; event: 'signed' | 'poSent' | 'confirmed' | 'transit' }[]
}

export const approvals: ApprovalFixture[] = [
  {
    id: 'ap_1',
    status: 'sign',
    note: 'secondMissing',
    title: 'Motor trifásico 4 kW · 60 ud',
    amount: '17.140,00 €',
    seller: 'Vendedor E',
    signatures: [
      { slot: 'first', who: 'Responsable · compras', when: 'Hoy 10:42', signed: true },
      { slot: 'second', who: '', when: '', signed: false },
    ],
    documents: [
      { kind: 'rfq', hash: 'sha256 3b9f…a210', available: true },
      { kind: 'po', available: false },
      { kind: 'certificate', available: false },
    ],
    tracking: [],
  },
  {
    id: 'ap_2',
    status: 'sign',
    note: 'highAmount',
    title: 'Compresor de tornillo · 12 ud',
    amount: '64.044,40 €',
    seller: 'Vendedor G',
    signatures: [
      { slot: 'first', who: '', when: '', signed: false },
      { slot: 'second', who: '', when: '', signed: false },
    ],
    documents: [
      { kind: 'rfq', hash: 'sha256 77c1…0d4e', available: true },
      { kind: 'po', available: false },
      { kind: 'certificate', available: false },
    ],
    tracking: [],
  },
  {
    id: 'ap_3',
    status: 'progress',
    note: 'inTransit',
    title: 'Correa trapezoidal B-68 · 300 ud',
    amount: '4.210,00 €',
    seller: 'Vendedor N',
    signatures: [
      { slot: 'first', who: 'Responsable · compras', when: '05/11 09:12', signed: true },
      { slot: 'second', who: 'Finanzas', when: '05/11 09:30', signed: true },
    ],
    documents: [
      { kind: 'rfq', hash: 'sha256 a04c…91bb', available: true },
      { kind: 'po', hash: 'sha256 5e12…c3f0', available: true },
      { kind: 'certificate', hash: 'sha256 e8d9…7a65', available: true },
    ],
    tracking: [
      { when: '05/11 09:12', event: 'signed' },
      { when: '05/11 09:40', event: 'poSent' },
      { when: '06/11 16:03', event: 'confirmed' },
      { when: '08/11 11:20', event: 'transit' },
    ],
  },
]
