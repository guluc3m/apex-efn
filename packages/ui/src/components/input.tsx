import * as React from 'react'

import { cn } from '../lib/utils.js'

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>

/** El borde pasa a acento en `press`; el foco se ve al instante (outline global). */
const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      'box-border min-h-9 w-full border border-control-border bg-bg px-2.5 text-ink transition-[border-color] duration-(--press) ease-apex placeholder:text-ink-muted focus:border-accent disabled:cursor-not-allowed disabled:border-line disabled:text-ink-muted',
      className,
    )}
    {...props}
  />
))
Input.displayName = 'Input'

export { Input }
