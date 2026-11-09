import { setRequestLocale } from 'next-intl/server'

import { SigningView } from '@/components/signing/signing-view'
import { signingKeys } from '@/fixtures/signing-keys'
import { user } from '@/fixtures/user'

// //todo_#147: el rol vendrá de la sesión; `?rol=viewer` solo permite ver el estado de solo lectura con la fixture
export default async function SigningPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>
  searchParams: Promise<{ rol?: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)
  const { rol } = await searchParams
  return <SigningView keys={signingKeys} role={rol === 'viewer' ? 'viewer' : user.role} />
}
