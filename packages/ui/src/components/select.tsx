import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'
import * as React from 'react'

import { raised } from '../lib/styles.js'
import { cn } from '../lib/utils.js'

import { Icon } from './icon.js'
import { Label } from './label.js'

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps {
  label: string
  options: SelectOption[]
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  placeholder?: string
  /** Oculta la etiqueta visible; sigue siendo el nombre accesible. */
  hideLabel?: boolean
  /** Deshabilitado: la página debe mostrar el motivo junto al control. */
  disabled?: boolean
  className?: string
}

export function Select({ label, options, hideLabel, placeholder, className, ...root }: SelectProps) {
  const id = React.useId()
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      {!hideLabel && <Label htmlFor={id}>{label}</Label>}
      <SelectPrimitive.Root {...root}>
        <SelectPrimitive.Trigger
          id={id}
          aria-label={hideLabel ? label : undefined}
          className="group flex min-h-9 w-full cursor-pointer items-center justify-between gap-2 border border-control-border bg-bg px-2.5 text-ink transition-[border-color] duration-(--press) ease-apex data-[state=open]:border-accent disabled:cursor-not-allowed disabled:border-line disabled:text-ink-muted"
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon className="flex text-ink-muted transition-transform duration-(--fast) ease-apex-move group-data-[state=open]:rotate-180 motion-reduce:transition-none">
            <Icon icon={ChevronDown} />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            position="popper"
            sideOffset={4}
            className={cn(
              raised,
              'z-60 w-(--radix-select-trigger-width) min-w-(--radix-select-trigger-width) py-1 data-[state=closed]:animate-[ap-out_var(--exit)_var(--easing)_forwards] data-[state=open]:animate-[ap-persiana_var(--fast)_var(--easing-move)] motion-reduce:animate-none',
            )}
          >
            <SelectPrimitive.Viewport>
              {options.map((o) => (
                <SelectPrimitive.Item
                  key={o.value}
                  value={o.value}
                  className="flex min-h-9 cursor-pointer items-center gap-2 pr-3 pl-2 whitespace-nowrap text-ink outline-none data-highlighted:bg-line"
                >
                  <span className="inline-flex w-4 flex-none">
                    <SelectPrimitive.ItemIndicator>
                      <Icon icon={Check} />
                    </SelectPrimitive.ItemIndicator>
                  </span>
                  <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </div>
  )
}
