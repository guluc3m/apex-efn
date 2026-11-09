import { notFound } from 'next/navigation'
import { setRequestLocale } from 'next-intl/server'

import { ApprovalDetail } from '@/components/approvals/approvals-view'
import { approvals } from '@/fixtures/approvals'

export default async function ApprovalPage({ params }: { params: Promise<{ locale: string; approvalId: string }> }) {
  const { locale, approvalId } = await params
  setRequestLocale(locale)
  const a = approvals.find((x) => x.id === approvalId)
  if (!a) notFound()
  return <ApprovalDetail a={a} />
}
