import * as React from 'react'

import { cn } from '../lib/utils.js'

import { Label } from './label.js'

export interface FieldControlProps {
  id: string
  'aria-describedby': string | undefined
  'aria-invalid': true | undefined
}

export interface FieldProps {
  label: string
  /** Ayuda debajo del campo, en `small`. */
  hint?: string
  /** Error ya traducido. Sustituye a la ayuda y marca el control como inválido. */
  error?: string
  /** El control recibe `id`, `aria-describedby` y `aria-invalid`; ahí se enlazan etiqueta, ayuda y error. */
  children: (control: FieldControlProps) => React.ReactNode
  className?: string
}

/** Etiqueta encima, ayuda y error debajo (DESIGN §6). Valida el llamador al salir del campo y al enviar. */
export function Field({ label, hint, error, children, className }: FieldProps) {
  const id = React.useId()
  const note = error ?? hint
  const noteId = note ? `${id}-note` : undefined
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <Label htmlFor={id}>{label}</Label>
      {children({ id, 'aria-describedby': noteId, 'aria-invalid': error ? true : undefined })}
      {note && (
        <span
          id={noteId}
          className={cn('text-[13px] leading-[1.45]', error ? 'text-bad' : 'text-ink-muted')}
        >
          {note}
        </span>
      )}
    </div>
  )
}
