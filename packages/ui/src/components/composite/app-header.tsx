import { LogOut } from 'lucide-react'
import * as React from 'react'

import { cn } from '../../lib/utils.js'
import { Icon } from '../icon.js'

import { anchor, type RenderLink } from './link.js'
import { NavItems, type NavItem } from './nav-links.js'

export interface AppHeaderProps {
  navLabel: string
  items: NavItem[]
  skipLabel: string
  /** Destino del salto: id del contenido principal, con `#`. */
  skipHref?: string
  brand: React.ReactNode
  /** Aviso junto a la navegación (p. ej. datos financieros caducados). */
  notice?: React.ReactNode
  /** Indicador de firma, selector de idioma… */
  trailing?: React.ReactNode
  signOut?: { label: string; href: string }
  renderLink?: RenderLink
  className?: string
}

export function AppHeader({ navLabel, items, skipLabel, skipHref = '#contenido', brand, notice, trailing, signOut, renderLink = anchor, className }: AppHeaderProps) {
  return (
    <header
      className={cn(
        'relative flex min-h-[57px] flex-wrap items-center justify-between gap-4 px-6 py-2.5 [background:linear-gradient(90deg,var(--accent-line),var(--line)_70%)_bottom/100%_1px_no-repeat,var(--bg)]',
        className,
      )}
    >
      <a href={skipHref} className="absolute -top-full left-2 z-70 bg-accent px-3 py-2 text-on-accent focus:top-2">
        {skipLabel}
      </a>
      <nav aria-label={navLabel} className="flex flex-wrap items-center gap-5">
        {brand}
        <NavItems items={items} renderLink={renderLink} itemClass="py-1" />
        {notice}
      </nav>
      <div className="ml-auto flex items-center gap-3">
        {trailing}
        {signOut &&
          renderLink({
            href: signOut.href,
            className: 'inline-flex items-center gap-1.5 py-1 text-[13px] text-ink-soft no-underline hover:text-ink',
            children: (
              <>
                <Icon icon={LogOut} />
                {signOut.label}
              </>
            ),
          })}
      </div>
    </header>
  )
}
