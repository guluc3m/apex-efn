import { setRequestLocale } from 'next-intl/server'

import { ApprovalsList } from '@/components/approvals/approvals-view'
import { APPROVAL_TABS, approvals } from '@/fixtures/approvals'

export default async function ApprovalsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>
  searchParams: Promise<{ estado?: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)
  const { estado } = await searchParams
  const status = APPROVAL_TABS.find((s) => s === estado) ?? 'sign'
  return <ApprovalsList rows={approvals} status={status} />
}
