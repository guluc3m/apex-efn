'use client'

import { Input, Label, Select } from '@apex/ui'
import { useTranslations } from 'next-intl'
import { useId, type ReactNode } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

/** Mensaje de error del campo `name` (clave de `onboarding.errors.*`), o undefined. */
function useError(name: string) {
  const { getFieldState, formState } = useFormContext()
  const t = useTranslations('onboarding.errors')
  const message = getFieldState(name, formState).error?.message
  return message ? t(message) : undefined
}

function ErrorText({ id, children }: { id: string; children?: string }) {
  return children ? (
    <span id={id} className="text-[13px] text-bad">
      {children}
    </span>
  ) : null
}

export function TextField({ name, label, hint, long, className }: { name: string; label: string; hint?: string; long?: boolean; className?: string }) {
  const { register } = useFormContext()
  const id = useId()
  const error = useError(name)
  const props = { id, 'aria-invalid': error ? true : undefined, 'aria-describedby': error ? `${id}-e` : undefined, ...register(name) }
  return (
    <div className={`flex flex-col gap-1 ${className ?? ''}`}>
      <Label htmlFor={id}>{label}</Label>
      {long ? (
        <textarea rows={3} className="box-border w-full border border-control-border bg-bg px-2.5 py-2 text-ink transition-[border-color] duration-(--press) ease-apex focus:border-accent aria-invalid:border-bad" {...props} />
      ) : (
        <Input className="aria-invalid:border-bad" placeholder={hint} {...props} />
      )}
      <ErrorText id={`${id}-e`}>{error}</ErrorText>
    </div>
  )
}

/** Campo suelto dentro de una tabla: etiqueta accesible, error enlazado. */
export function CellInput({ name, label, describedBy }: { name: string; label: string; describedBy?: string }) {
  const { register } = useFormContext()
  const error = useError(name)
  return (
    <Input
      aria-label={label}
      aria-invalid={error ? true : undefined}
      aria-describedby={error ? describedBy : undefined}
      title={error}
      className="w-36 text-right aria-invalid:border-bad"
      {...register(name)}
    />
  )
}

export function SelectField({ name, label, options }: { name: string; label: string; options: { value: string; label: string }[] }) {
  const { control } = useFormContext()
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => <Select label={label} options={options} value={field.value as string} onValueChange={field.onChange} />}
    />
  )
}

export function CheckGroup({ name, legend, options }: { name: string; legend: string; options: { value: string; label: string }[] }) {
  const { register } = useFormContext()
  return (
    <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
      <legend className="mb-2 p-0 text-[13px] text-ink-muted">{legend}</legend>
      {options.map((o) => (
        <CheckRow key={o.value} label={o.label}>
          <input type="checkbox" value={o.value} className="accent-accent" {...register(name)} />
        </CheckRow>
      ))}
    </fieldset>
  )
}

export function CheckRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex items-center gap-2 text-ink">
      {children}
      {label}
    </label>
  )
}
