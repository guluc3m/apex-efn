'use client'

import { useEffect, useRef, useState } from 'react'

import { LoginField } from './login-field'

/**
 * Monta el campo de puntos (WebGL2). `onField` entrega el motor (o null al desmontar) para subir `hoverT`.
 * Sin WebGL2 muestra una imagen estática del campo.
 */
export function LoginFieldCanvas({ onField }: { onField: (field: LoginField | null) => void }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [fallback, setFallback] = useState(false)
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const field = new LoginField(cv)
    if (!field.start()) {
      field.stop()
      setFallback(true)
      return
    }
    onField(field)
    return () => {
      field.stop()
      onField(null)
    }
  }, [onField])
  return (
    <>
      <canvas
        ref={ref}
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 block"
        hidden={fallback}
      />
      {fallback && (
        // eslint-disable-next-line @next/next/no-img-element -- fondo decorativo, ya optimizado
        <img
          src="/login-field.webp"
          alt=""
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 size-full object-cover"
        />
      )}
    </>
  )
}
