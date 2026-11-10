import { setRequestLocale } from 'next-intl/server'
import type { ReactNode } from 'react'

import { AppShell } from '@/components/app-shell'
import { getViewer } from '@/lib/viewer'

// Grupo de rutas autenticadas: cabecera + navegación. Las pantallas nuevas van en este directorio.
export default async function AppLayout({ children, params }: { children: ReactNode; params: Promise<{ locale: string }> }) {
  setRequestLocale((await params).locale)
  return <AppShell viewer={await getViewer()}>{children}</AppShell>
}
