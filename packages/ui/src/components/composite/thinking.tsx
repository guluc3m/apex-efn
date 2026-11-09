import * as React from 'react'

import { ShiningText } from '../shining-text.js'

// Intervalos irregulares fijos dentro de 1,6–2,4 s: sin azar, reproducibles.
const INTERVALS = [1600, 2100, 1800, 2400]

export interface ThinkingProps {
  /** Frases reales del proceso, en orden. Con menos de dos no hay relevo. */
  phrases: string[]
  active?: boolean
  className?: string
}

/** Relevo vertical de 160 ms a intervalos irregulares de 1,6 a 2,4 s. Sin movimiento, el cambio es directo. */
export function Thinking({ phrases, active = true, className }: ThinkingProps) {
  const [i, setI] = React.useState(0)
  React.useEffect(() => {
    if (!active || phrases.length < 2) return
    const id = setTimeout(() => setI((n) => (n + 1) % phrases.length), INTERVALS[i % INTERVALS.length])
    return () => clearTimeout(id)
  }, [i, active, phrases.length])

  return (
    <span key={i} className="inline-block motion-safe:animate-[ap-msg_160ms_var(--easing)_both]">
      <ShiningText className={className}>{phrases[i % Math.max(phrases.length, 1)] ?? ''}</ShiningText>
    </span>
  )
}
