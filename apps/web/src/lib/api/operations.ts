import type {
  AbortNegotiationResponse,
  ActivateFinancialSnapshotData,
  ActivateFinancialSnapshotResponse,
  ApproveNegotiationDraftData,
  ApproveNegotiationDraftResponse,
  CloseSigningSessionResponse,
  CreateDecisionData,
  CreateDecisionResponse,
  CreateMissionData,
  CreateMissionResponse,
  CreateOnboardingSessionData,
  ListIntakeMessagesResponse,
  SendIntakeMessageData,
  SendIntakeMessageResponse,
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
  GetOnboardingSessionResponse,
  ListCategoriesResponse,
  ListMissionsData,
  ListOnboardingSessionsResponse,
  ListMissionsResponse,
  ListMissionOffersData,
  ListMissionOffersResponse,
  GetNegotiationResponse,
  ConnectAccountData,
  ConnectAccountResponse,
  DisconnectAccountResponse,
  ListConnectedAccountsResponse,
  ListNegotiationMessagesResponse,
  NotifyFinanceOfApprovalResponse,
  ListDealsData,
  ListDealsResponse,
  ListGateQueueData,
  ListGateQueueResponse,
  GetApprovalResponse,
  GetDecisionResponse,
  ListApprovalsData,
  ListApprovalsResponse,
  GetSigningSessionResponse,
  ListAuditEventsData,
  ListAuditEventsResponse,
  ListMySigningKeysResponse,
  OpenSigningSessionData,
  OpenSigningSessionResponse,
  ProposeConfigChangeData,
  ProposeConfigChangeResponse,
  RegisterMySigningKeyData,
  RegisterMySigningKeyResponse,
  RejectNegotiationDraftResponse,
  ReopenNegotiationResponse,
  ResumeNegotiationResponse,
  SendHumanNegotiationMessageData,
  SendHumanNegotiationMessageResponse,
  TakeoverNegotiationResponse,
  TranslateNegotiationMessageData,
  TranslateNegotiationMessageResponse,
  RevokeSigningKeyData,
  RevokeSigningKeyResponse,
  SignDecisionData,
  SignDecisionResponse,
  VerifyAuditChainResponse,
  VerifyDecisionResponse,
  GetFinancialImportResponse,
  ListConfigVersionsResponse,
  SuggestFinancialCsvMappingResponse,
  PauseMissionResponse,
  ResumeMissionResponse,
  CancelMissionResponse,
  ListProfilesResponse,
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

    /** Categories the tenant already has; suggestions only, there is no global catalog. */
    listCategories: (signal?: AbortSignal) =>
      client.request<ListCategoriesResponse>('/v1/categories', { path: undefined, signal }),

    /** The wizard's saved draft: the session with its per-step progress. */
    getOnboardingSession: (id: string, signal?: AbortSignal) =>
      client.request<GetOnboardingSessionResponse>('/v1/onboarding/sessions/{id}', { path: { id }, signal }),

    /** Newest first. `limit: 1` finds the tenant's current session. */
    listOnboardingSessions: (query?: { limit?: number }, signal?: AbortSignal) =>
      client.request<ListOnboardingSessionsResponse>('/v1/onboarding/sessions', { path: undefined, query, signal }),

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

    listIntakeMessages: (id: string, signal?: AbortSignal) =>
      client.request<ListIntakeMessagesResponse>('/v1/onboarding/sessions/{id}/messages', { path: { id }, signal }),

    /** One IntakeAgent turn: the user message, the reply and the session with any profile fields it filled in. */
    sendIntakeMessage: (id: string, body: SendIntakeMessageData['body'], signal?: AbortSignal) =>
      client.request<SendIntakeMessageResponse>('/v1/onboarding/sessions/{id}/messages', {
        method: 'POST',
        path: { id },
        body,
        signal,
      }),

    /** Header row only reaches the model. A suggestion: the buyer confirms it before the upload. */
    suggestFinancialCsvMapping: (onboardingId: string, file: File, signal?: AbortSignal) => {
      const body = new FormData()
      body.append('file', file)
      return client.request<SuggestFinancialCsvMappingResponse>('/v1/onboarding/{id}/financial-csv/mapping', {
        method: 'POST',
        path: { id: onboardingId },
        body,
        signal,
      })
    },

    /** Multipart upload; the server parses it and returns a draft import. Nothing is activated. */
    uploadFinancialCsv: (onboardingId: string, file: File, columnMapping?: Record<string, string>, signal?: AbortSignal) => {
      const body = new FormData()
      body.append('file', file)
      if (columnMapping && Object.keys(columnMapping).length > 0) body.append('column_mapping', JSON.stringify(columnMapping))
      return client.request<UploadFinancialCsvResponse>('/v1/onboarding/{id}/financial-csv', {
        method: 'POST',
        path: { id: onboardingId },
        body,
        signal,
      })
    },

    /** One import with its report, addressed by import id (the report page is a route by id). */
    getFinancialImport: (onboardingId: string, importId: string, signal?: AbortSignal) =>
      client.request<GetFinancialImportResponse>('/v1/onboarding/{id}/financial-csv/{import_id}', {
        path: { id: onboardingId, import_id: importId },
        signal,
      }),

    /** Creates the activation decision (pending signature). It does not activate anything by itself. */
    activateFinancialSnapshot: (
      onboardingId: string,
      body: ActivateFinancialSnapshotData['body'],
      signal?: AbortSignal,
    ) =>
      client.request<ActivateFinancialSnapshotResponse>('/v1/onboarding/{id}/financial-csv/activate', {
        method: 'POST',
        path: { id: onboardingId },
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

    /** The server builds the document (ranking, contributions, trade-offs, versions); the UI never does. */
    exportMissionRecommendation: (id: string, profile: string, format: 'pdf' | 'csv' | 'json', signal?: AbortSignal) =>
      client.blob('/v1/missions/{id}/recommendation/export', { path: { id }, query: { profile, format }, signal }),

    /** The server renders the PDF from the signed decision; 409 `not_signed` until every signature is in. */
    downloadApprovalDocument: (id: string, kind: 'rfq' | 'po' | 'certificate', signal?: AbortSignal) =>
      client.blob('/v1/approvals/{id}/documents/{kind}', { path: { id, kind }, signal }),

    notifyFinanceOfApproval: (id: string) =>
      client.request<NotifyFinanceOfApprovalResponse>('/v1/approvals/{id}/notify-finance', { method: 'POST', path: { id } }),

    listConnectedAccounts: (signal?: AbortSignal) =>
      client.request<ListConnectedAccountsResponse>('/v1/connected-accounts', { path: undefined, signal }),

    /** The credentials go straight to the server's vault; the response only has the status and an opaque ref. */
    connectAccount: (body: ConnectAccountData['body']) =>
      client.request<ConnectAccountResponse>('/v1/connected-accounts', { method: 'POST', path: undefined, body }),

    disconnectAccount: (id: string) =>
      client.request<DisconnectAccountResponse>('/v1/connected-accounts/{id}', { method: 'DELETE', path: { id } }),

    listMissions: (query?: ListMissionsData['query'], signal?: AbortSignal) =>
      client.request<ListMissionsResponse>('/v1/missions', { path: undefined, query, signal }),

    getMission: (id: string, signal?: AbortSignal) =>
      client.request<GetMissionResponse>('/v1/missions/{id}', { path: { id }, signal }),

    pauseMission: (id: string, signal?: AbortSignal) =>
      client.request<PauseMissionResponse>('/v1/missions/{id}/pause', { method: 'POST', path: { id }, signal }),

    resumeMission: (id: string, signal?: AbortSignal) =>
      client.request<ResumeMissionResponse>('/v1/missions/{id}/resume', { method: 'POST', path: { id }, signal }),

    cancelMission: (id: string, signal?: AbortSignal) =>
      client.request<CancelMissionResponse>('/v1/missions/{id}/cancel', { method: 'POST', path: { id }, signal }),

    listMissionOffers: (id: string, query?: ListMissionOffersData['query'], signal?: AbortSignal) =>
      client.request<ListMissionOffersResponse>('/v1/missions/{id}/offers', { path: { id }, query, signal }),

    /** Ranking profiles the user can pick for a recommendation. */
    listProfiles: (signal?: AbortSignal) => client.request<ListProfilesResponse>('/v1/profiles', { path: {}, signal }),

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

    listApprovals: (query?: ListApprovalsData['query'], signal?: AbortSignal) =>
      client.request<ListApprovalsResponse>('/v1/approvals', { path: undefined, query, signal }),

    getApproval: (id: string, signal?: AbortSignal) =>
      client.request<GetApprovalResponse>('/v1/approvals/{id}', { path: { id }, signal }),

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

    /** Configuration history, newest first. */
    listConfigVersions: (signal?: AbortSignal) =>
      client.request<ListConfigVersionsResponse>('/v1/config/versions', { path: {}, signal }),

    proposeConfigChange: (body: ProposeConfigChangeData['body'], signal?: AbortSignal) =>
      client.request<ProposeConfigChangeResponse>('/v1/config/proposals', {
        method: 'POST',
        path: undefined,
        body,
        signal,
      }),

    listAuditEvents: (query?: ListAuditEventsData['query'], signal?: AbortSignal) =>
      client.request<ListAuditEventsResponse>('/v1/audit', { path: undefined, query, signal }),

    verifyAuditChain: (signal?: AbortSignal) =>
      client.request<VerifyAuditChainResponse>('/v1/audit/verify', { path: undefined, signal }),

    verifyDecision: (id: string, signal?: AbortSignal) =>
      client.request<VerifyDecisionResponse>('/v1/decisions/{id}/verify', { method: 'POST', path: { id }, signal }),

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

    translateNegotiationMessage: (id: string, messageId: string, targetLanguage: TranslateNegotiationMessageData['body']['target_language']) =>
      client.request<TranslateNegotiationMessageResponse>('/v1/negotiations/{id}/messages/{message_id}/translate', {
        method: 'POST',
        path: { id, message_id: messageId },
        body: { target_language: targetLanguage },
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
    reopenNegotiation: (id: string, reason?: string) =>
      client.request<ReopenNegotiationResponse>('/v1/negotiations/{id}/reopen', {
        method: 'POST',
        path: { id },
        body: reason ? { reason } : undefined,
      }),

    getSigningSession: (id: string, signal?: AbortSignal) =>
      client.request<GetSigningSessionResponse>('/v1/signing-sessions/{id}', { path: { id }, signal }),

    closeSigningSession: (id: string, signal?: AbortSignal) =>
      client.request<CloseSigningSessionResponse>('/v1/signing-sessions/{id}', { method: 'DELETE', path: { id }, signal }),

    createDecision: (body: CreateDecisionData['body'], signal?: AbortSignal) =>
      client.request<CreateDecisionResponse>('/v1/decisions', { method: 'POST', path: undefined, body, signal }),

    getDecision: (id: string, signal?: AbortSignal) =>
      client.request<GetDecisionResponse>('/v1/decisions/{id}', { path: { id }, signal }),

    signDecision: (id: string, body: SignDecisionData['body'], signal?: AbortSignal) =>
      client.request<SignDecisionResponse>('/v1/decisions/{id}/sign', { method: 'POST', path: { id }, body, signal }),

    revokeSigningKey: (id: string, body: RevokeSigningKeyData['body'], signal?: AbortSignal) =>
      client.request<RevokeSigningKeyResponse>('/v1/keys/{id}/revoke', { method: 'POST', path: { id }, body, signal }),
  }
}

export type Operations = ReturnType<typeof createOperations>
