import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { cn } from '../../lib/utils.js'
import { Icon } from '../icon.js'

import { anchor, type RenderLink } from './link.js'

export interface NavItem {
  label: string
  href: string
  icon: LucideIcon
  current?: boolean
}

export interface NavProps {
  /** Nombre accesible de la navegación. */
  label: string
  items: NavItem[]
  renderLink?: RenderLink
  className?: string
}

interface NavItemsProps {
  items: NavItem[]
  renderLink?: RenderLink
  itemClass?: string
  currentClass?: string
}

/** Línea de 2 px en `accent` bajo el elemento actual: la regla señala, no se pulsa. */
export function NavItems({ items, renderLink = anchor, itemClass, currentClass }: NavItemsProps) {
  return items.map((it) =>
    React.createElement(
      React.Fragment,
      { key: it.href },
      renderLink({
        href: it.href,
        ...(it.current ? { 'aria-current': 'page' as const } : {}),
        className: cn(
          'inline-flex items-center gap-1.5 no-underline shadow-[inset_0_-2px_0_transparent] transition-[color,background-color] duration-(--fast) hover:text-ink',
          it.current ? cn('text-ink shadow-[inset_0_-2px_0_var(--accent)]', currentClass) : 'text-ink-soft',
          itemClass,
        ),
        children: (
          <>
            <Icon icon={it.icon} size={20} />
            {it.label}
          </>
        ),
      }),
    ),
  )
}
