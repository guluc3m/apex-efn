import type {
  CreateMissionData,
  CreateMissionResponse,
  CreateOnboardingSessionData,
  CreateOnboardingSessionResponse,
  CreateSourcingRequestData,
  CreateSourcingRequestResponse,
  GetEffectiveConfigData,
  GetEffectiveConfigResponse,
  GetMissionResponse,
  UpdateOnboardingSessionData,
  UpdateOnboardingSessionResponse,
} from '@apex/shared-types/contracts'

import type { ApiClient } from './client'

/**
 * Typed operations. Request and response types come from the generated contract, so a contract
 * change that breaks a call site fails `pnpm typecheck` instead of failing at runtime.
 *
 * Only the operations screens use today are wrapped. The D6-09b issues add the rest here, one
 * operation at a time, as the matching orchestrator route stops answering 501.
 */
export function createOperations(client: ApiClient) {
  return {
    createOnboardingSession: (body: CreateOnboardingSessionData['body'], signal?: AbortSignal) =>
      client.request<CreateOnboardingSessionResponse>('/v1/onboarding/sessions', {
        method: 'POST',
        path: undefined,
        body,
        signal,
      }),

    updateOnboardingSession: (
      id: UpdateOnboardingSessionData['path']['id'],
      body: UpdateOnboardingSessionData['body'],
      signal?: AbortSignal,
    ) =>
      client.request<UpdateOnboardingSessionResponse>('/v1/onboarding/sessions/{id}', {
        method: 'PATCH',
        path: { id },
        body,
        signal,
      }),

    createSourcingRequest: (body: CreateSourcingRequestData['body'], signal?: AbortSignal) =>
      client.request<CreateSourcingRequestResponse>('/v1/sourcing-requests', {
        method: 'POST',
        path: undefined,
        body,
        signal,
      }),

    createMission: (body: CreateMissionData['body'], signal?: AbortSignal) =>
      client.request<CreateMissionResponse>('/v1/missions', {
        method: 'POST',
        path: undefined,
        body,
        signal,
      }),

    getMission: (id: string, signal?: AbortSignal) =>
      client.request<GetMissionResponse>('/v1/missions/{id}', { path: { id }, signal }),

    getEffectiveConfig: (query?: GetEffectiveConfigData['query'], signal?: AbortSignal) =>
      client.request<GetEffectiveConfigResponse>('/v1/config/effective', {
        path: undefined,
        query,
        signal,
      }),
  }
}

export type Operations = ReturnType<typeof createOperations>
