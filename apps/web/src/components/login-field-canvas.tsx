'use client'

import { useEffect, useRef } from 'react'

import { LoginField } from './login-field'

/** Monta el campo de puntos. `onField` entrega el motor (o null al desmontar) para subir `hoverT`. */
export function LoginFieldCanvas({ onField }: { onField: (field: LoginField | null) => void }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const field = new LoginField(cv)
    field.start()
    onField(field)
    return () => {
      field.stop()
      onField(null)
    }
  }, [onField])
  return <canvas ref={ref} aria-hidden="true" className="pointer-events-none absolute inset-0 block" />
}
