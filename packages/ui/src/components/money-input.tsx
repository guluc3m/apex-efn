import * as React from 'react'

import { cn } from '../lib/utils.js'

import { Input, type InputProps } from './input.js'

export interface MoneyInputProps extends Omit<InputProps, 'type' | 'inputMode'> {
  /** Divisa explícita junto al importe. */
  currency: 'EUR' | 'USD' | 'CNY'
}

/** Importe decimal como texto con divisa visible, nunca `type="number"` (DESIGN §6). Solo captura: no calcula ni redondea. */
export const MoneyInput = React.forwardRef<HTMLInputElement, MoneyInputProps>(
  ({ currency, className, ...props }, ref) => (
    <div className={cn('flex items-stretch', className)}>
      <Input
        ref={ref}
        inputMode="decimal"
        autoComplete="off"
        spellCheck={false}
        className="text-right"
        {...props}
      />
      <span className="border-control-border bg-panel text-ink-soft flex items-center border border-l-0 px-2.5 font-mono text-[13px]">
        {currency}
      </span>
    </div>
  )
)
MoneyInput.displayName = 'MoneyInput'
