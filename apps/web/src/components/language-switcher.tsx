'use client'

import { LanguageSwitcher, type LanguageOption } from '@apex/ui'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Suspense } from 'react'

import { locales } from '@/i18n/routing'

// Cada idioma con su nombre en su propio idioma; no se traduce.
const OPTIONS: Record<(typeof locales)[number], LanguageOption> = {
  es: { id: 'es', name: 'Español', code: 'ES', lang: 'es' },
  en: { id: 'en', name: 'English', code: 'EN', lang: 'en' },
  zh: { id: 'zh', name: '简体中文', code: 'ZH', lang: 'zh-Hans' },
  he: { id: 'he', name: 'עברית', code: 'HE', lang: 'he' },
}

/** Cambia el prefijo de idioma conservando la página y la query. */
function Switcher() {
  const locale = useLocale()
  const pathname = usePathname()
  const router = useRouter()
  const query = useSearchParams().toString()
  const t = useTranslations('shell.language')
  const options = locales.map((l) => OPTIONS[l])
  const current = OPTIONS[locale as keyof typeof OPTIONS] ?? OPTIONS.es

  return (
    <LanguageSwitcher
      options={options}
      value={current.id}
      label={t('button', { name: current.name })}
      menuLabel={t('menu')}
      onChange={(id) => {
        const rest = pathname.split('/').slice(2).join('/')
        // La ruta se arma dinámicamente: typedRoutes no puede comprobarla.
        router.push(`/${id}${rest ? `/${rest}` : ''}${query ? `?${query}` : ''}` as never)
      }}
    />
  )
}

// useSearchParams exige Suspense para no romper el prerender estático.
export function AppLanguageSwitcher() {
  return (
    <Suspense fallback={null}>
      <Switcher />
    </Suspense>
  )
}
