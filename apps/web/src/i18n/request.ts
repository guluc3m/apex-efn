import type { AbstractIntlMessages } from 'next-intl'
import { getRequestConfig } from 'next-intl/server'

import { defaultLocale, isLocale } from './routing'

// Lista fija: cada dominio escribe solo en su archivo messages/<locale>/<ns>.json.
const namespaces = [
  'common', 'shell', 'onboarding', 'missions', 'negotiation', 'decisions',
  'gate', 'compare', 'sellers', 'signing', 'approvals', 'company', 'states',
] as const

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale
  const locale = isLocale(requested) ? requested : defaultLocale
  const entries = await Promise.all(
    namespaces.map(async (ns) => {
      const mod = (await import(`../../messages/${locale}/${ns}.json`)) as { default: AbstractIntlMessages }
      return [ns, mod.default] as const
    }),
  )
  return { locale, messages: Object.fromEntries(entries) }
})
