import type { ReactNode } from 'react'

import { CompanyShell } from '@/components/app-shell'
import { getViewer } from '@/lib/viewer'

export default async function CompanyLayout({ children }: { children: ReactNode }) {
  return <CompanyShell role={(await getViewer()).role}>{children}</CompanyShell>
}
