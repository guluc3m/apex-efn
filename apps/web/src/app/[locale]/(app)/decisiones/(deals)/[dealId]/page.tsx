import { notFound } from 'next/navigation'
import { setRequestLocale } from 'next-intl/server'

import { deals } from '@/fixtures/decisions'

// //todo_#148: validar contra GET /v1/dashboard/deals/{id}
export default async function DealPage({ params }: { params: Promise<{ locale: string; dealId: string }> }) {
  const { locale, dealId } = await params
  setRequestLocale(locale)
  if (!deals.some((d) => d.id === dealId)) notFound()
  return null
}
