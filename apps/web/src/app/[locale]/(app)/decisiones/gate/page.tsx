import { setRequestLocale } from 'next-intl/server'
import { Suspense } from 'react'

import { GateQueue } from '@/components/gate/gate-queue'
import { gateQueue } from '@/fixtures/gate'
import { user } from '@/fixtures/user'

export default async function GatePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  return (
    <Suspense>
      <GateQueue items={gateQueue} role={user.role} />
    </Suspense>
  )
}
