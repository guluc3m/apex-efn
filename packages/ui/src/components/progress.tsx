import * as ProgressPrimitive from '@radix-ui/react-progress'
import * as React from 'react'

import { cn } from '../lib/utils.js'

const TONES = { accent: 'bg-accent', warn: 'bg-warn', bad: 'bg-bad' } as const

/** Barra de 6 px: línea que señala, no se pulsa. */
const Progress = React.forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> & { tone?: keyof typeof TONES }
>(({ className, value, tone = 'accent', ...props }, ref) => (
  <ProgressPrimitive.Root ref={ref} value={value} className={cn('relative h-1.5 w-full overflow-hidden bg-line', className)} {...props}>
    <ProgressPrimitive.Indicator
      className={cn('h-full w-full', TONES[tone])}
      // ponytail: el desplazamiento depende del valor; no hay clase estática.
      style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
    />
  </ProgressPrimitive.Root>
))
Progress.displayName = 'Progress'

export { Progress }
