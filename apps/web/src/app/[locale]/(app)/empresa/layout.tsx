import type { ReactNode } from 'react'

import { CompanyShell } from '@/components/app-shell'

export default function CompanyLayout({ children }: { children: ReactNode }) {
  return <CompanyShell>{children}</CompanyShell>
}
