import { setRequestLocale } from 'next-intl/server'

import { LoginPanel } from '@/components/login-panel'

export default async function AccessPage({ params }: { params: Promise<{ locale: string }> }) {
  setRequestLocale((await params).locale)
  return <LoginPanel />
}
