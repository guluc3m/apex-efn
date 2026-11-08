import * as React from 'react'

import { cn } from '../lib/utils.js'

export interface ShiningTextProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Text to show. `children` takes precedence when both are given. */
  text?: string
  /** Set to false when the text is decorative and another element already announces the state. */
  announce?: boolean
}

/**
 * Animated "the agent is working" label (DESIGN.md §8, ShiningText).
 *
 * A highlight sweeps across the text in a loop. It is the only looping animation allowed in the UI and
 * is reserved for work an agent is doing right now (thinking, drafting a message, searching offers).
 * The effect lives in the `text-shine` utility in globals.css, so this stays a server component and
 * needs no animation library. Under prefers-reduced-motion the text is static and muted.
 */
const ShiningText = React.forwardRef<HTMLSpanElement, ShiningTextProps>(
  ({ text, announce = true, className, children, ...props }, ref) => (
    <span
      ref={ref}
      role={announce ? 'status' : undefined}
      aria-live={announce ? 'polite' : undefined}
      className={cn('text-shine', className)}
      {...props}
    >
      {children ?? text}
    </span>
  )
)
ShiningText.displayName = 'ShiningText'

export { ShiningText }
