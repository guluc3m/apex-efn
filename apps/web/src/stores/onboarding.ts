import { create } from 'zustand'

import type { Drafts, FormStepId } from '@/components/onboarding/schemas'
import { initialDrafts } from '@/fixtures/onboarding'

export interface CsvSelection {
  name: string
  size: number
}

// Borrador del alta. Nunca guarda credenciales de plataformas ni el contenido del CSV.
// //todo_#152: persistir el borrador en el servidor (guardado automático)
interface OnboardingStore {
  drafts: Drafts
  csv: CsvSelection | null
  save: <K extends FormStepId>(step: K, values: Drafts[K]) => void
  setCsv: (csv: CsvSelection | null) => void
}

export const useOnboarding = create<OnboardingStore>((set) => ({
  drafts: initialDrafts,
  csv: null,
  save: (step, values) => set((s) => ({ drafts: { ...s.drafts, [step]: values } })),
  setCsv: (csv) => set({ csv }),
}))
