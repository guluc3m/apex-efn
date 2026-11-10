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
  setSessionId: (id: string) => void
  save: <K extends FormStepId>(step: K, values: Drafts[K]) => void
  setCsv: (csv: CsvSelection | null) => void
}

export const useOnboarding = create<OnboardingStore>((set) => ({
  drafts: initialDrafts,
  csv: null,
  sessionId: null,
  setSessionId: (sessionId) => set({ sessionId }),
  save: (step, values) => set((s) => ({ drafts: { ...s.drafts, [step]: values } })),
  setCsv: (csv) => set({ csv }),
}))
