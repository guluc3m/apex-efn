import type { UploadFinancialCsvResponse } from '@apex/shared-types/contracts'
import { create } from 'zustand'

import type { Drafts, FormStepId } from '@/components/onboarding/schemas'
import { initialDrafts } from '@/fixtures/onboarding'

export interface CsvSelection {
  name: string
  size: number
}

// Borrador del alta. Nunca guarda credenciales de plataformas ni el contenido del CSV.
// Los pasos empresa y sector se guardan en el servidor al validarse (`sessionId`); el resto aún no tiene contrato.
interface OnboardingStore {
  drafts: Drafts
  csv: CsvSelection | null
  sessionId: string | null
  financialImport: UploadFinancialCsvResponse | null
  setFinancialImport: (i: UploadFinancialCsvResponse | null) => void
  setSessionId: (id: string) => void
  /** Replace the company and sector drafts with what the server saved. */
  restore: (values: Pick<Drafts, 'empresa' | 'sector'>) => void
  /** Bumped when the agent changes a draft, so a mounted form remounts with the new values. */
  draftsRevision: number
  applyAgentDraft: <K extends FormStepId>(step: K, values: Drafts[K]) => void
  /** Adds a budget and negotiation row for a free-text category (ignored when it already exists). */
  addCategory: (name: string) => void
  save: <K extends FormStepId>(step: K, values: Drafts[K]) => void
  setCsv: (csv: CsvSelection | null) => void
}

export const useOnboarding = create<OnboardingStore>((set) => ({
  drafts: initialDrafts,
  csv: null,
  sessionId: null,
  financialImport: null,
  setFinancialImport: (financialImport) => set({ financialImport }),
  setSessionId: (sessionId) => set({ sessionId }),
  draftsRevision: 0,
  restore: (values) => set((s) => ({ drafts: { ...s.drafts, ...values }, draftsRevision: s.draftsRevision + 1 })),
  applyAgentDraft: (step, values) => set((s) => ({ drafts: { ...s.drafts, [step]: values }, draftsRevision: s.draftsRevision + 1 })),
  addCategory: (name) =>
    set((s) => {
      const label = name.trim()
      const exists = s.drafts.presupuesto.categorias.some((c) => c.label.toLowerCase() === label.toLowerCase())
      if (!label || exists) return s
      const id = label.toLowerCase()
      return {
        drafts: {
          ...s.drafts,
          presupuesto: { ...s.drafts.presupuesto, categorias: [...s.drafts.presupuesto.categorias, { id, label, envelope: '', maximo: '' }] },
          negociacion: { ...s.drafts.negociacion, categorias: [...s.drafts.negociacion.categorias, { id, label, objetivo: '', maximo: '' }] },
        },
        draftsRevision: s.draftsRevision + 1,
      }
    }),
  save: (step, values) => set((s) => ({ drafts: { ...s.drafts, [step]: values } })),
  setCsv: (csv) => set({ csv }),
}))
