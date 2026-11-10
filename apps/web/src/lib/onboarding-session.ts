import { api } from '@/lib/api'
import { useOnboarding } from '@/stores/onboarding'

/** The session id, creating the session on first use. The base currency comes from the budget draft. */
export async function ensureSession(): Promise<string> {
  const { sessionId, drafts, setSessionId } = useOnboarding.getState()
  if (sessionId) return sessionId
  const created = await api.createOnboardingSession({ base_currency: drafts.presupuesto.divisa as 'EUR' | 'USD' | 'CNY' })
  setSessionId(created.id)
  return created.id
}
