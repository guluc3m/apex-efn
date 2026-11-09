import { setRequestLocale } from 'next-intl/server'

import { ErrorPanel } from '@/components/error-panel'

export default async function ForbiddenPage({ params }: { params: Promise<{ locale: string }> }) {
  setRequestLocale((await params).locale)
  return <ErrorPanel kind="forbidden" />
}
