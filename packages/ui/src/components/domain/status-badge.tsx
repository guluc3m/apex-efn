import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { Badge, type BadgeProps } from '../badge.js'
import { Popover, PopoverContent, PopoverTrigger } from '../popover.js'

export type StatusTone = NonNullable<BadgeProps['tone']>

export interface StatusBadgeProps {
  tone: StatusTone
  /** Icono del estado: el color nunca es la única señal (DESIGN §4). */
  icon?: LucideIcon
  /** Texto visible, traducido por el llamador. */
  label: string
  /** El porqué del estado: si existe, el badge abre un Popover con él. */
  breakdown?: React.ReactNode
  breakdownTitle?: string
}

/** Base de los badges de dominio: tono + icono + texto. */
export function StatusBadge({ tone, icon, label, breakdown, breakdownTitle }: StatusBadgeProps) {
  const badge = (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  )
  if (breakdown === undefined) return badge
  return (
    <Popover>
      <PopoverTrigger className="inline-flex cursor-pointer appearance-none border-0 bg-transparent p-0">
        {badge}
      </PopoverTrigger>
      <PopoverContent title={breakdownTitle}>{breakdown}</PopoverContent>
    </Popover>
  )
}
