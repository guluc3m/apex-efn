'use client'

import { createContext, useContext, type ReactNode } from 'react'

import type { Viewer } from '@/lib/viewer'

const ViewerContext = createContext<Viewer>({ role: 'viewer', userId: null, tenantId: null })

export const ViewerProvider = ({ viewer, children }: { viewer: Viewer; children: ReactNode }) => (
  <ViewerContext.Provider value={viewer}>{children}</ViewerContext.Provider>
)

export const useViewer = () => useContext(ViewerContext)
