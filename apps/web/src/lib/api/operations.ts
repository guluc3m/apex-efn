import type {
  AbortNegotiationResponse,
  ApproveNegotiationDraftData,
  ApproveNegotiationDraftResponse,
  CreateMissionData,
  CreateMissionResponse,
  CreateOnboardingSessionData,
  CreateOnboardingSessionResponse,
  CreateSourcingRequestData,
  CreateSourcingRequestResponse,
  ApplyDealActionData,
  ApplyDealActionResponse,
  ApplyGateQueueActionData,
  ApplyGateQueueActionResponse,
  GetEffectiveConfigData,
  GetEffectiveConfigResponse,
  GetMissionRecommendationData,
  GetMissionRecommendationResponse,
  GetMissionResponse,
  GetSellerConfidenceData,
  GetSellerConfidenceResponse,
  ListMissionOffersData,
  ListMissionOffersResponse,
  GetNegotiationResponse,
  ListNegotiationMessagesResponse,
  ListDealsData,
  ListDealsResponse,
  ListGateQueueData,
  ListGateQueueResponse,
  ListMySigningKeysResponse,
  OpenSigningSessionData,
  OpenSigningSessionResponse,
  ProposeConfigChangeData,
  ProposeConfigChangeResponse,
  RegisterMySigningKeyData,
  RegisterMySigningKeyResponse,
  RejectNegotiationDraftResponse,
  ResumeNegotiationResponse,
  SendHumanNegotiationMessageData,
  SendHumanNegotiationMessageResponse,
  TakeoverNegotiationResponse,
  UploadFinancialCsvResponse,
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

    /** Multipart upload; the server parses it and returns a draft import. Nothing is activated. */
    uploadFinancialCsv: (onboardingId: string, file: File, signal?: AbortSignal) => {
      const body = new FormData()
      body.append('file', file)
      return client.request<UploadFinancialCsvResponse>('/v1/onboarding/{id}/financial-csv', {
        method: 'POST',
        path: { id: onboardingId },
        body,
        signal,
      })
    },

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

    listMissionOffers: (id: string, query?: ListMissionOffersData['query'], signal?: AbortSignal) =>
      client.request<ListMissionOffersResponse>('/v1/missions/{id}/offers', { path: { id }, query, signal }),

    getMissionRecommendation: (id: string, profile: GetMissionRecommendationData['query']['profile'], signal?: AbortSignal) =>
      client.request<GetMissionRecommendationResponse>('/v1/missions/{id}/recommendation', {
        path: { id },
        query: { profile },
        signal,
      }),

    getSellerConfidence: (id: string, query?: GetSellerConfidenceData['query'], signal?: AbortSignal) =>
      client.request<GetSellerConfidenceResponse>('/v1/sellers/{id}/confidence', { path: { id }, query, signal }),

    listDeals: (query?: ListDealsData['query'], signal?: AbortSignal) =>
      client.request<ListDealsResponse>('/v1/dashboard/deals', { path: undefined, query, signal }),

    /** Creates a decision waiting for its signature. It never signs anything. */
    applyDealAction: (id: string, body: ApplyDealActionData['body'], signal?: AbortSignal) =>
      client.request<ApplyDealActionResponse>('/v1/dashboard/deals/{id}/actions', {
        method: 'POST',
        path: { id },
        body,
        signal,
      }),

    listGateQueue: (query?: ListGateQueueData['query'], signal?: AbortSignal) =>
      client.request<ListGateQueueResponse>('/v1/gate/queue', { path: undefined, query, signal }),

    /** Creates a decision waiting for its signature. It never signs anything. */
    applyGateQueueAction: (id: string, body: ApplyGateQueueActionData['body'], signal?: AbortSignal) =>
      client.request<ApplyGateQueueActionResponse>('/v1/gate/queue/{id}/actions', {
        method: 'POST',
        path: { id },
        body,
        signal,
      }),

    getEffectiveConfig: (query?: GetEffectiveConfigData['query'], signal?: AbortSignal) =>
      client.request<GetEffectiveConfigResponse>('/v1/config/effective', {
        path: undefined,
        query,
        signal,
      }),

    proposeConfigChange: (body: ProposeConfigChangeData['body'], signal?: AbortSignal) =>
      client.request<ProposeConfigChangeResponse>('/v1/config/proposals', {
        method: 'POST',
        path: undefined,
        body,
        signal,
      }),

    listMySigningKeys: (signal?: AbortSignal) =>
      client.request<ListMySigningKeysResponse>('/v1/keys/me', { path: undefined, signal }),

    registerMySigningKey: (body: RegisterMySigningKeyData['body'], signal?: AbortSignal) =>
      client.request<RegisterMySigningKeyResponse>('/v1/keys/me', {
        method: 'POST',
        path: undefined,
        body,
        signal,
      }),

    openSigningSession: (body: OpenSigningSessionData['body'], signal?: AbortSignal) =>
      client.request<OpenSigningSessionResponse>('/v1/signing-sessions', {
        method: 'POST',
        path: undefined,
        body,
        signal,
      }),

    getNegotiation: (id: string, signal?: AbortSignal) =>
      client.request<GetNegotiationResponse>('/v1/negotiations/{id}', { path: { id }, signal }),

    listNegotiationMessages: (id: string, cursor?: string, signal?: AbortSignal) =>
      client.request<ListNegotiationMessagesResponse>('/v1/negotiations/{id}/messages', {
        path: { id },
        query: { cursor, limit: 200 },
        signal,
      }),

    sendHumanNegotiationMessage: (id: string, body: SendHumanNegotiationMessageData['body']) =>
      client.request<SendHumanNegotiationMessageResponse>('/v1/negotiations/{id}/messages', {
        method: 'POST',
        path: { id },
        body,
      }),

    approveNegotiationDraft: (id: string, body: ApproveNegotiationDraftData['body']) =>
      client.request<ApproveNegotiationDraftResponse>('/v1/negotiations/{id}/approve', {
        method: 'POST',
        path: { id },
        body,
      }),

    rejectNegotiationDraft: (id: string, body: ApproveNegotiationDraftData['body']) =>
      client.request<RejectNegotiationDraftResponse>('/v1/negotiations/{id}/reject', {
        method: 'POST',
        path: { id },
        body,
      }),

    takeoverNegotiation: (id: string, reason?: string) =>
      client.request<TakeoverNegotiationResponse>('/v1/negotiations/{id}/takeover', {
        method: 'POST',
        path: { id },
        body: reason ? { reason } : undefined,
      }),

    resumeNegotiation: (id: string, reason?: string) =>
      client.request<ResumeNegotiationResponse>('/v1/negotiations/{id}/resume', {
        method: 'POST',
        path: { id },
        body: reason ? { reason } : undefined,
      }),

    abortNegotiation: (id: string, reason?: string) =>
      client.request<AbortNegotiationResponse>('/v1/negotiations/{id}/abort', {
        method: 'POST',
        path: { id },
        body: reason ? { reason } : undefined,
      }),
  }
}

export type Operations = ReturnType<typeof createOperations>
