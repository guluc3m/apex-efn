import { setRequestLocale } from 'next-intl/server'
import { Suspense } from 'react'

import { GateQueue } from '@/components/gate/gate-queue'
import { gateQueue } from '@/fixtures/gate'
import { getViewer } from '@/lib/viewer'

export default async function GatePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  return (
    <Suspense>
      <GateQueue items={gateQueue} role={(await getViewer()).role} />
    </Suspense>
  )
}
