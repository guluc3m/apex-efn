'use client'

import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'

import { cn } from '../lib/utils.js'

import { shiningClass } from './shining-text.js'
import { Tooltip } from './tooltip.js'

const buttonVariants = cva(
  'inline-flex box-border items-center justify-center gap-2 border font-medium whitespace-nowrap no-underline transition-[background-color,border-color,color,translate] duration-(--fast) ease-apex active:translate-y-px active:duration-(--press) [&_svg]:flex-none',
  {
    variants: {
      variant: { pri: '', sec: '', ghost: '', danger: '' },
      size: { sm: 'min-h-8 px-2.5', md: 'min-h-9 px-3.5', lg: 'min-h-11 px-4' },
      state: {
        ready: 'cursor-pointer',
        inert: 'cursor-not-allowed border-line bg-transparent text-ink-muted active:translate-y-0',
        busy: 'cursor-progress border-control-border bg-raised text-ink active:translate-y-0',
      },
    },
    compoundVariants: [
      { state: 'ready', variant: 'sec', class: 'border-control-border bg-panel text-ink hover:border-ink-muted hover:bg-raised' },
      { state: 'ready', variant: 'pri', class: 'border-accent bg-accent text-on-accent hover:border-accent-hover hover:bg-accent-hover' },
      { state: 'ready', variant: 'ghost', class: 'border-transparent bg-transparent text-ink-soft hover:bg-panel hover:text-ink' },
      { state: 'ready', variant: 'danger', class: 'border-danger bg-danger text-white hover:border-danger-hover hover:bg-danger-hover' },
    ],
    defaultVariants: { variant: 'sec', size: 'md', state: 'ready' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    Omit<VariantProps<typeof buttonVariants>, 'state'> {
  asChild?: boolean
  /** Ocupado: conserva el ancho, ShiningText en el texto y sin spinner. */
  busy?: boolean
  /** Deshabilitado con motivo: sigue enfocable y el motivo llega por aria-describedby (tooltip). */
  disabledReason?: string
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, busy, disabledReason, disabled, onClick, children, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    const inert = Boolean(disabled || disabledReason)
    const state = inert ? 'inert' : busy ? 'busy' : 'ready'
    const button = (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, state }), className)}
        {...(disabledReason ? { 'aria-disabled': true } : { disabled })}
        aria-busy={busy || undefined}
        onClick={disabledReason || busy ? (e: React.MouseEvent<HTMLButtonElement>) => e.preventDefault() : onClick}
        {...props}
      >
        {busy && typeof children === 'string' ? <span className={shiningClass}>{children}</span> : children}
      </Comp>
    )
    return disabledReason ? <Tooltip text={disabledReason}>{button}</Tooltip> : button
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
