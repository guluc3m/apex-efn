import { setRequestLocale } from 'next-intl/server'

import { ApprovalDetail } from '@/components/approvals/approvals-view'

export default async function ApprovalPage({ params }: { params: Promise<{ locale: string; approvalId: string }> }) {
  const { locale, approvalId } = await params
  setRequestLocale(locale)
  return <ApprovalDetail id={approvalId} />
}
