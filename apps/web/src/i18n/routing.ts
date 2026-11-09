export const locales = ['es', 'en', 'zh', 'he'] as const
export type Locale = (typeof locales)[number]
export const defaultLocale: Locale = 'es'

export const isLocale = (v: string | undefined): v is Locale => locales.includes(v as Locale)
