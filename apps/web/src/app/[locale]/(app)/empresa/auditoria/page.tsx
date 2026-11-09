import { setRequestLocale } from 'next-intl/server'

import { AuditView } from '@/components/company/audit-view'
import { user } from '@/fixtures/user'

// //todo_#147: el rol vendrá de la sesión; `?rol=admin` solo permite ver la tabla con la fixture
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>
  searchParams: Promise<{ rol?: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)
  const { rol } = await searchParams
  return <AuditView role={rol === 'admin' ? 'admin' : user.role} />
}
