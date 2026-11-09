import * as React from 'react'

import { cn } from '../lib/utils.js'

/** Solo para trabajo que un agente hace ahora. Con movimiento reducido queda estático en ink-muted. */
export const shiningClass =
  'bg-[linear-gradient(110deg,var(--ink-muted)_35%,var(--ink)_50%,var(--ink-muted)_75%)] bg-[length:200%_100%] bg-clip-text text-transparent animate-[ap-shine_2s_linear_infinite] motion-reduce:animate-none motion-reduce:bg-none motion-reduce:text-ink-muted'

export function ShiningText({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span role="status" className={cn(shiningClass, className)} {...props} />
}
