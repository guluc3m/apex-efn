'use client'

import { useMutation, useQuery, type QueryClient } from '@tanstack/react-query'

import { createApiClient } from './client'
import { createOperations } from './operations'
import { ApiError } from './problem'

export const api = createOperations(createApiClient())

export const queryKeys = {
  mission: (id: string) => ['mission', id] as const,
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

export function useEffectiveConfig(category?: string) {
  return useQuery({
    queryKey: queryKeys.effectiveConfig(category),
    queryFn: ({ signal }) => api.getEffectiveConfig(category ? { category } : undefined, signal),
  })
}

export function useCreateSourcingRequest() {
  return useMutation({ mutationFn: (body: Parameters<typeof api.createSourcingRequest>[0]) => api.createSourcingRequest(body) })
}

export function useCreateMission() {
  return useMutation({ mutationFn: (body: Parameters<typeof api.createMission>[0]) => api.createMission(body) })
}
