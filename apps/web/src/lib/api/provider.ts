'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { createApiClient } from './client'

/**
 * Tenant-wide OpenAI-compatible provider settings.
 *
 * The orchestrator route is being built in parallel and is not in the generated contract yet, so
 * the types live here. `api_key` is deliberately absent: the server only says whether one is
 * stored (`api_key_set`) and never returns the secret.
 */
export interface LlmProviderSettings {
  base_url: string | null
  model: string | null
  api_key_set: boolean
  updated_at: string | null
}

export interface LlmProviderTestResult {
  ok: boolean
  models: string[]
  error: string | null
}

/**
 * Body of the PUT. `api_key` is omitted when the user leaves the field empty: by contract an
 * omitted or empty key keeps the stored one, while `null` would clear it. The UI has no
 * "clear the key but keep the endpoint" action, so it never sends `null`.
 */
export interface LlmProviderInput {
  base_url: string
  model: string
  api_key?: string
}

export const providerQueryKey = ['settings', 'llm-provider'] as const

/** Operations against `/v1/settings/llm-provider`; the BFF catch-all prefixes `/api`. */
export function createProviderApi(client = createApiClient()) {
  return {
    get: (signal?: AbortSignal) =>
      client.request<LlmProviderSettings>('/v1/settings/llm-provider', { path: undefined, signal }),

    /** PUT may answer 200 with the settings, 200 with no body or 204; the query is refetched either way. */
    save: async (body: LlmProviderInput) => {
      try {
        await client.request<unknown>('/v1/settings/llm-provider', { method: 'PUT', path: undefined, body })
      } catch (error) {
        // A 2xx with an empty body is still a successful save; the refetch is the source of truth.
        if (error instanceof SyntaxError) return
        throw error
      }
    },

    clear: async () => {
      await client.request<void>('/v1/settings/llm-provider', { method: 'DELETE', path: undefined })
    },

    test: () =>
      client.request<LlmProviderTestResult>('/v1/settings/llm-provider/test', { method: 'POST', path: undefined }),
  }
}

export type ProviderApi = ReturnType<typeof createProviderApi>

const providerApi = createProviderApi()

export function useLlmProvider() {
  return useQuery({ queryKey: providerQueryKey, queryFn: ({ signal }) => providerApi.get(signal) })
}

export function useSaveLlmProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: LlmProviderInput) => providerApi.save(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: providerQueryKey }),
  })
}

export function useClearLlmProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => providerApi.clear(),
    onSuccess: () => qc.invalidateQueries({ queryKey: providerQueryKey }),
  })
}

/** The test uses the saved configuration, so it never sends the form state. */
export function useTestLlmProvider() {
  return useMutation({ mutationFn: () => providerApi.test() })
}

/** Suggested model identifiers. They are data, not copy, so they stay out of the message files. */
export const MODEL_PRESETS = ['deepseek-chat', 'gpt-4o-mini', 'gpt-4.1-mini', 'llama3.1', 'qwen2.5'] as const

/** Trims the form and omits an empty key so the server keeps the one it already has. */
export function buildProviderPayload(baseUrl: string, model: string, apiKey: string): LlmProviderInput {
  const key = apiKey.trim()
  return { base_url: baseUrl.trim(), model: model.trim(), ...(key ? { api_key: key } : {}) }
}

/** http(s) URL with a host. The server validates again; this only blocks an obviously wrong save. */
export function isValidBaseUrl(value: string): boolean {
  try {
    const url = new URL(value.trim())
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.host !== ''
  } catch {
    return false
  }
}
