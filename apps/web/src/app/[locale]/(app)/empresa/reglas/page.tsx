import { setRequestLocale } from 'next-intl/server'

import { RulesView } from '@/components/company/rules-view'

// //todo_#167: el permiso de cambio (finance, admin, owner) vendrá de la sesión; //todo_#147
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  return <RulesView />
}
