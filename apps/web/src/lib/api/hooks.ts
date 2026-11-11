'use client'

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { createApiClient } from './client'
import { createOperations } from './operations'
import { ApiError } from './problem'

export const api = createOperations(createApiClient())

export const queryKeys = {
  mission: (id: string) => ['mission', id] as const,
  missionOffers: (id: string) => ['mission', id, 'offers'] as const,
  recommendation: (id: string, profile: string) => ['mission', id, 'recommendation', profile] as const,
  sellerConfidence: (id: string) => ['seller', id, 'confidence'] as const,
  negotiation: (id: string) => ['negotiation', id] as const,
  negotiationMessages: (id: string) => ['negotiation', id, 'messages'] as const,
  deals: (query?: object) => ['deals', query ?? null] as const,
  gateQueue: (query?: object) => ['gate', 'queue', query ?? null] as const,
  effectiveConfig: (category?: string) => ['config', 'effective', category ?? null] as const,
}

/** Client errors (4xx) are final answers; only network and 5xx failures are worth retrying. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
  return failureCount < 2
}

export function applyQueryDefaults(client: QueryClient): QueryClient {
  client.setDefaultOptions({
    queries: { staleTime: 60 * 1000, refetchOnWindowFocus: false, retry: shouldRetry },
    mutations: { retry: false },
  })
  return client
}

export function useMission(id: string) {
  return useQuery({
    queryKey: queryKeys.mission(id),
    queryFn: ({ signal }) => api.getMission(id, signal),
  })
}

/** First page (the API maximum) of offers; the matrix filters and sorts it locally. */
export function useMissionOffers(id: string) {
  return useQuery({
    queryKey: queryKeys.missionOffers(id),
    queryFn: ({ signal }) => api.listMissionOffers(id, { limit: 200 }, signal),
  })
}

export function useMissionRecommendation(id: string, profile: string | undefined) {
  return useQuery({
    queryKey: queryKeys.recommendation(id, profile ?? ''),
    queryFn: ({ signal }) => api.getMissionRecommendation(id, profile!, signal),
    enabled: !!profile,
  })
}

export function useSellerConfidence(id: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.sellerConfidence(id),
    queryFn: ({ signal }) => api.getSellerConfidence(id, { limit: 10 }, signal),
    enabled,
  })
}

export function useEffectiveConfig(category?: string) {
  return useQuery({
    queryKey: queryKeys.effectiveConfig(category),
    queryFn: ({ signal }) => api.getEffectiveConfig(category ? { category } : undefined, signal),
  })
}

export function useCreateSourcingRequest() {
  return useMutation({ mutationFn: (body: Parameters<typeof api.createSourcingRequest>[0]) => api.createSourcingRequest(body) })
}

export function useProposeConfigChange() {
  return useMutation({ mutationFn: (body: Parameters<typeof api.proposeConfigChange>[0]) => api.proposeConfigChange(body) })
}

export function useCreateMission() {
  return useMutation({ mutationFn: (body: Parameters<typeof api.createMission>[0]) => api.createMission(body) })
}

/** A new draft or seller message has no push channel here, so the screen polls while it is open. */
const NEGOTIATION_POLL_MS = 5000

export function useNegotiation(id: string) {
  return useQuery({
    queryKey: queryKeys.negotiation(id),
    queryFn: ({ signal }) => api.getNegotiation(id, signal),
    refetchInterval: NEGOTIATION_POLL_MS,
  })
}

export function useNegotiationMessages(id: string) {
  return useQuery({
    queryKey: queryKeys.negotiationMessages(id),
    queryFn: ({ signal }) => api.listNegotiationMessages(id, undefined, signal),
    refetchInterval: NEGOTIATION_POLL_MS,
  })
}

export type NegotiationAction = 'approve' | 'reject' | 'takeover' | 'resume' | 'abort' | 'reopen' | 'send'

/** One mutation for every write on a negotiation; the server answer is the only source of truth, so refetch after it. */
export function useNegotiationAction(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ action, draftId, text, reason }: { action: NegotiationAction; draftId?: string; text?: string; reason?: string }): Promise<unknown> => {
      switch (action) {
        case 'approve':
          return api.approveNegotiationDraft(id, { draft_id: draftId ?? '' })
        case 'reject':
          return api.rejectNegotiationDraft(id, { draft_id: draftId ?? '' })
        case 'takeover':
          return api.takeoverNegotiation(id, reason)
        case 'resume':
          return api.resumeNegotiation(id, reason)
        case 'abort':
          return api.abortNegotiation(id, reason)
        case 'reopen':
          return api.reopenNegotiation(id, reason)
        case 'send':
          return api.sendHumanNegotiationMessage(id, { content: text ?? '' })
      }
    },
    onSettled: () => qc.invalidateQueries({ queryKey: queryKeys.negotiation(id) }),
  })
}

export function useDeals(query?: Parameters<typeof api.listDeals>[0]) {
  return useQuery({ queryKey: queryKeys.deals(query), queryFn: ({ signal }) => api.listDeals(query, signal) })
}

export function useGateQueue(query?: Parameters<typeof api.listGateQueue>[0]) {
  return useQuery({ queryKey: queryKeys.gateQueue(query), queryFn: ({ signal }) => api.listGateQueue(query, signal) })
}

/** Both mutations only create a decision pending signature; the lists are refreshed afterwards. */
export function useDealAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; body: Parameters<typeof api.applyDealAction>[1] }) => api.applyDealAction(v.id, v.body),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['deals'] }), qc.invalidateQueries({ queryKey: ['gate'] })]),
  })
}

export function useGateAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; body: Parameters<typeof api.applyGateQueueAction>[1] }) => api.applyGateQueueAction(v.id, v.body),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['deals'] }), qc.invalidateQueries({ queryKey: ['gate'] })]),
  })
}
