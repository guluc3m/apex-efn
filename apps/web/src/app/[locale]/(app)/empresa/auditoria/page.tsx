import { setRequestLocale } from 'next-intl/server'

import { AuditView } from '@/components/company/audit-view'
import { getViewer } from '@/lib/viewer'

export default async function Page({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)
  return <AuditView role={(await getViewer()).role} />
}
