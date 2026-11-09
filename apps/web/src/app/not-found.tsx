import { Geist, Geist_Mono } from 'next/font/google'
import { NextIntlClientProvider } from 'next-intl'
import { getMessages } from 'next-intl/server'

import '@/styles/globals.css'
import { ErrorPanel } from '@/components/error-panel'
import { defaultLocale } from '@/i18n/routing'

const geist = Geist({ subsets: ['latin'], variable: '--font-geist' })
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono' })

// 404 fuera de /[locale]: el layout raíz no tiene <html>, así que lo define esta página.
export default async function GlobalNotFound() {
  const messages = await getMessages({ locale: defaultLocale })
  return (
    <html lang={defaultLocale} className={`${geist.variable} ${geistMono.variable}`}>
      <body className="font-sans">
        <NextIntlClientProvider locale={defaultLocale} messages={messages}>
          <ErrorPanel kind="notFound" />
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
