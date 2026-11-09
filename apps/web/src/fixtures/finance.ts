// //todo_#153: sustituir por GET /v1/onboarding/{id}/financial-csv (ImportReport) y el snapshot derivado; hoy todo viene ya calculado.
export type RejectReason = 'decimals' | 'period' | 'metric' | 'currency' | 'duplicate'

export interface FinanceImport {
  file: string
  rows: number
  accepted: number
  rejected: number
  duplicated: number
  periods: number
  periodRange: string
  converted: number
  mapping: { column: string; field: string }[]
  rejections: { metric: string; period: string; line: number; value: string; reason: RejectReason; keptLine?: number }[]
  warnings: ('fx' | 'taxReserve')[]
  taxReserveMonth: string
}

export interface FinanceSummary {
  referenceDate: string
  netCapacity: string
  buffer: number
  buyingPowerScore: number
  replaces: string
  expires: string
  payloadHash: string
  envelopes: { key: string; name: string; used: string; usedPct: number; available: string; limit: string; nearlyExhausted: boolean }[]
}

// //todo_#153: ImportReport real del backend
export const financeImport: FinanceImport = {
  file: 'finanzas_2026-10.csv',
  rows: 48,
  accepted: 43,
  rejected: 4,
  duplicated: 1,
  periods: 3,
  periodRange: '2026-08 / 2026-10',
  converted: 6,
  mapping: [
    { column: 'saldo_caja', field: 'cash_balance' },
    { column: 'linea_credito_disp', field: 'credit_line_available' },
  ],
  rejections: [
    { metric: 'payroll', period: '2026-09', line: 12, value: '4812500,5', reason: 'decimals' },
    { metric: 'revenue', period: '2026-9', line: 19, value: '18200000', reason: 'period' },
    { metric: 'inventory', period: '2026-10', line: 27, value: '920000', reason: 'metric' },
    { metric: 'accounts_payable', period: '2026-10', line: 33, value: '2100000 GBP', reason: 'currency' },
    { metric: 'cash_balance', period: '2026-10', line: 41, value: '6400000', reason: 'duplicate', keptLine: 8 },
  ],
  warnings: ['fx', 'taxReserve'],
  taxReserveMonth: '2026-10',
}

// //todo_#153: snapshot derivado real del backend
export const financeSummary: FinanceSummary = {
  referenceDate: '31/10/2026',
  netCapacity: '41.300,00 €',
  buffer: 15,
  buyingPowerScore: 64,
  replaces: 'Septiembre',
  expires: '15/12/2026',
  payloadHash: '7c1e…b08a',
  envelopes: [
    { key: 'bearings', name: 'Rodamientos', used: '6.600,00 €', usedPct: 26, available: '18.400,00 €', limit: '25.000,00 €', nearlyExhausted: false },
    { key: 'valves', name: 'Válvulas', used: '13.900,00 €', usedPct: 77, available: '4.100,00 €', limit: '18.000,00 €', nearlyExhausted: false },
    { key: 'cables', name: 'Cable y sensores', used: '8.400,00 €', usedPct: 93, available: '600,00 €', limit: '9.000,00 €', nearlyExhausted: true },
  ],
}
