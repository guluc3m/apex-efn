import type { LucideIcon } from 'lucide-react'
import type * as React from 'react'

import { cn } from '../lib/utils.js'

import { Icon } from './icon.js'

export interface EmptyStateProps {
  icon: LucideIcon
  /** Concreto: «No tienes nada pendiente», nunca «Sin datos». */
  title: string
  description?: string
  /** Siguiente paso: normalmente un `Button`. */
  actions?: React.ReactNode
  className?: string
}

/** Estado vacío (DESIGN §6): un icono, un título concreto y una acción. */
export function EmptyState({ icon, title, description, actions, className }: EmptyStateProps) {
  return (
    <div className={cn('border-line bg-panel box-border border p-8', className)}>
      <strong className="flex items-center gap-2.5 font-semibold">
        <Icon icon={icon} size={20} className="text-ink-muted" />
        {title}
      </strong>
      {description && <p className="text-ink-soft m-0 mt-1">{description}</p>}
      {actions && <div className="mt-3 flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
