import { Suspense, type ReactNode } from 'react'

import { DecisionsView } from '@/components/decisions/decisions-view'
import { getViewer } from '@/lib/viewer'

// La vista vive en el layout: cambiar de trato o abrir la transcripción no la remonta (conserva scroll y foco).
export default async function DecisionsLayout({ children }: { children: ReactNode }) {
  const { role } = await getViewer()
  return (
    <>
      <Suspense>
        <DecisionsView role={role} />
      </Suspense>
      {children}
    </>
  )
}
