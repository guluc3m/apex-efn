'use client'

import type { RenderLink } from '@apex/ui'
import Link from 'next/link'
import { useLocale } from 'next-intl'
import type { ComponentProps } from 'react'

type Props = Omit<ComponentProps<typeof Link>, 'href'> & { href: string }

/** `<Link>` de next con el prefijo de idioma. `href` va sin prefijo: `/decisiones`. */
export function AppLink({ href, ...props }: Props) {
  const locale = useLocale()
  const target = href.startsWith('/') ? `/${locale}${href === '/' ? '' : href}` : href
  // typedRoutes no ve las rutas de fases siguientes ni el prefijo dinámico.
  return <Link href={target as never} {...props} />
}

/** Para los `renderLink` de @apex/ui (AppHeader, CompanyNav, SigningSessionIndicator…). */
export const renderLink: RenderLink = ({ href, ...rest }) => <AppLink href={href} {...rest} />
