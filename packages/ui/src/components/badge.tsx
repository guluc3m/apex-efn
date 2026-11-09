import { CircleCheck, CircleHelp, OctagonAlert, type LucideIcon } from 'lucide-react'
import * as React from 'react'

import { cn } from '../lib/utils.js'

import { Icon } from './icon.js'

const TONES = {
  ok: { cls: 'bg-good-subtle text-good', icon: CircleCheck },
  warn: { cls: 'bg-warn-subtle text-warn', icon: null },
  bad: { cls: 'bg-bad-subtle text-bad', icon: OctagonAlert },
  neutro: { cls: 'bg-raised text-ink-soft', icon: CircleHelp },
  plano: { cls: 'bg-raised text-ink-soft', icon: null },
} as const

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: keyof typeof TONES
  /** Sustituye el icono del tono (conceptos de dominio). */
  icon?: LucideIcon
}

/** Estado = icono + color + texto. `warn` sin icono propio usa un triángulo relleno. */
function Badge({ tone = 'neutro', icon, className, children, ...props }: BadgeProps) {
  const t = TONES[tone]
  const glyph = icon ?? t.icon
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 px-2 py-0.5 text-[13px] leading-[1.45] whitespace-nowrap', t.cls, className)}
      {...props}
    >
      {glyph ? (
        <Icon icon={glyph} />
      ) : tone === 'warn' ? (
        <svg width="8.5" height="8" viewBox="0 0 8.5 8" aria-hidden="true" focusable="false" className="flex-none">
          <path d="M4.25 0 8.5 8H0Z" fill="currentColor" />
        </svg>
      ) : null}
      {children}
    </span>
  )
}

export { Badge }
