'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'

import { applyQueryDefaults } from '@/lib/api/hooks'
import { enableApiMocking } from '@/mocks/enable'

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => applyQueryDefaults(new QueryClient()))

  useEffect(() => {
    void enableApiMocking()
  }, [])

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
