import { setRequestLocale } from 'next-intl/server'

import { SigningView } from '@/components/signing/signing-view'
import { signingKeys } from '@/fixtures/signing-keys'
import { getViewer } from '@/lib/viewer'

export default async function SigningPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)
  return <SigningView keys={signingKeys} role={(await getViewer()).role} />
}
