import { setRequestLocale } from 'next-intl/server'

import { RulesView } from '@/components/company/rules-view'
import { RULE_CHANGE_ROLES } from '@/lib/config-rules'
import { getViewer } from '@/lib/viewer'

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  return <RulesView canChange={RULE_CHANGE_ROLES.includes((await getViewer()).role)} />
}
