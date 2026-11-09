import * as React from 'react'

import { cn } from '../lib/utils.js'

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
}

/** Casilla nativa con etiqueta clicable. Objetivo táctil de 24 px como mínimo (DESIGN §11). */
export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, className, ...props }, ref) => (
    <label
      className={cn(
        'text-ink has-disabled:text-ink-muted flex min-h-6 cursor-pointer items-center gap-2 has-disabled:cursor-not-allowed',
        className
      )}
    >
      <input ref={ref} type="checkbox" className="accent-accent size-4 flex-none" {...props} />
      {label}
    </label>
  )
)
Checkbox.displayName = 'Checkbox'
