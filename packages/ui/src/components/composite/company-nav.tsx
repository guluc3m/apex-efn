import { cn } from '../../lib/utils.js'

import { NavItems, type NavProps } from './nav-links.js'

/** Subnavegación de Empresa (UiEmpresaNav). */
export function CompanyNav({ label, items, renderLink, className }: NavProps) {
  return (
    <nav aria-label={label} className={cn('flex flex-wrap gap-1 border-b border-line px-8 py-2', className)}>
      <NavItems items={items} {...(renderLink ? { renderLink } : {})} itemClass="min-h-8 px-3" currentClass="bg-raised" />
    </nav>
  )
}
