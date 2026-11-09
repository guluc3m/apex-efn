import * as React from 'react'

import { raised } from '../lib/styles.js'
import { cn } from '../lib/utils.js'

export interface TooltipProps {
  text: string
  /** Un único elemento enfocable: recibe aria-describedby apuntando al tooltip (siempre montado). */
  children: React.ReactElement<{ 'aria-describedby'?: string }>
  className?: string
}

/** Hover y foco abren; Escape cierra sin mover el foco (WCAG 1.4.13). */
export function Tooltip({ text, children, className }: TooltipProps) {
  const id = React.useId()
  const [open, setOpen] = React.useState(false)
  // Escape cierra solo el tooltip: en captura sobre window, antes que el Dialog padre (Radix escucha en document).
  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      setOpen(false)
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open])
  return (
    <span
      className={cn('relative inline-flex', className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {React.cloneElement(children, {
        'aria-describedby': [children.props['aria-describedby'], id].filter(Boolean).join(' '),
      })}
      <span
        role="tooltip"
        id={id}
        data-state={open ? 'open' : 'closed'}
        className={cn(
          raised,
          'absolute top-[calc(100%+6px)] left-0 z-70 w-max max-w-70 px-2.5 py-1.5 text-[13px] leading-[1.45] font-normal whitespace-normal text-ink shadow-none',
          'before:absolute before:inset-x-0 before:-top-1.75 before:h-1.5 before:content-[""]',
          'transition-opacity duration-100 ease-apex data-[state=open]:delay-500 data-[state=closed]:invisible data-[state=closed]:opacity-0 data-[state=closed]:duration-(--exit)',
        )}
      >
        {text}
      </span>
    </span>
  )
}
