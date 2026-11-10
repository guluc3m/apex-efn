import { setRequestLocale } from 'next-intl/server'
import { Suspense } from 'react'

import { CompareView } from '@/components/compare/compare-view'

export default async function ComparePage({ params }: { params: Promise<{ locale: string; missionId: string }> }) {
  const { locale, missionId } = await params
  setRequestLocale(locale)
  // useSearchParams (the profile) needs a Suspense boundary.
  return (
    <Suspense>
      <CompareView missionId={missionId} />
    </Suspense>
  )
}
