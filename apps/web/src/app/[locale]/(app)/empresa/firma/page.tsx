import { setRequestLocale } from 'next-intl/server'

import { SigningView } from '@/components/signing/signing-view'
import { getViewer } from '@/lib/viewer'

export default async function SigningPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)
  const viewer = await getViewer()
  return <SigningView userId={viewer.userId} role={viewer.role} />
}
