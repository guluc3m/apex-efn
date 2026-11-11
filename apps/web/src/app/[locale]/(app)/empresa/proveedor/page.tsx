import { setRequestLocale } from 'next-intl/server'

import { ProviderView } from '@/components/company/provider-view'
import { getViewer } from '@/lib/viewer'

/** Only owner and admin may change the tenant-wide provider; everyone else sees it read-only. */
const PROVIDER_EDIT_ROLES: readonly string[] = ['admin', 'owner']

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  return <ProviderView canEdit={PROVIDER_EDIT_ROLES.includes((await getViewer()).role)} />
}
