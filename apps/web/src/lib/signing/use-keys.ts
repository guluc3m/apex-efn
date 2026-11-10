'use client'

import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'

export const signingKeysKey = ['signing', 'keys'] as const

export function useMySigningKeys() {
  return useQuery({ queryKey: signingKeysKey, queryFn: ({ signal }) => api.listMySigningKeys(signal) })
}
