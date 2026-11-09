import { Suspense, type ReactNode } from 'react'

import { DecisionsView } from '@/components/decisions/decisions-view'

// La vista vive en el layout: cambiar de trato o abrir la transcripción no la remonta (conserva scroll y foco).
export default function DecisionsLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Suspense>
        <DecisionsView />
      </Suspense>
      {children}
    </>
  )
}
