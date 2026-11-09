import { setRequestLocale } from 'next-intl/server'

import { CompareView } from '@/components/compare/compare-view'
import { COMPARE } from '@/fixtures/compare'

// //todo_#164: la comparativa vendrá del BFF por missionId
export default async function ComparePage({ params }: { params: Promise<{ locale: string; missionId: string }> }) {
  const { locale, missionId } = await params
  setRequestLocale(locale)
  return <CompareView data={COMPARE} missionId={missionId} />
}
