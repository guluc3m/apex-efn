import { setRequestLocale } from 'next-intl/server'

export default async function DecisionsPage({ params }: { params: Promise<{ locale: string }> }) {
  setRequestLocale((await params).locale)
  return null
}
