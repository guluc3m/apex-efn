import type { Metadata } from 'next'
import { Inter } from 'next/font/google'

import '@/styles/globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'APEX-EFN - B2B Sourcing Inteligente',
  description: 'Plataforma de sourcing inteligente y negociación automatizada de compras por volumen',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body className={inter.className}>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
