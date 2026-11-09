import type { LucideIcon } from 'lucide-react'

import { cn } from '../lib/utils.js'

export interface IconProps {
  icon: LucideIcon
  size?: 16 | 20
  /** Sin etiqueta el icono es decorativo (aria-hidden). */
  label?: string
  className?: string
}

export function Icon({ icon: Glyph, size = 16, label, className }: IconProps) {
  return (
    <Glyph
      size={size}
      strokeWidth={1.75}
      className={cn('block flex-none', className)}
      {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true })}
    />
  )
}
