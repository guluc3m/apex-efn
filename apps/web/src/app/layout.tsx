import type { Metadata } from 'next'
import type { ReactNode } from 'react'

export const metadata: Metadata = {
  title: 'Apex',
  icons: { icon: '/brand/apex-icono.svg' },
  description: 'Plataforma de sourcing inteligente y negociación automatizada de compras por volumen',
}

// El <html> y el <body> viven en app/[locale]/layout.tsx.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children
}
