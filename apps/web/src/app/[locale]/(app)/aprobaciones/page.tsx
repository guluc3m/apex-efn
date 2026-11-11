import { setRequestLocale } from 'next-intl/server'

import { ApprovalsList } from '@/components/approvals/approvals-view'

const TABS = ['sign', 'progress', 'closed'] as const

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
  return <ApprovalsList status={TABS.find((s) => s === estado) ?? 'sign'} />
}
