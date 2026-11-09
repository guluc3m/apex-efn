import type { Metadata } from 'next'
import type { ReactNode } from 'react'

export const metadata: Metadata = {
  title: 'APEX-EFN - B2B Sourcing Inteligente',
  description: 'Plataforma de sourcing inteligente y negociación automatizada de compras por volumen',
}

// El <html> y el <body> viven en app/[locale]/layout.tsx.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children
}
