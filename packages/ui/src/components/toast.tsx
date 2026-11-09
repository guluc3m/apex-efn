import * as ToastPrimitive from '@radix-ui/react-toast'
import { CircleCheck, CircleHelp, OctagonAlert, TriangleAlert, X, type LucideIcon } from 'lucide-react'
import * as React from 'react'

import { raised } from '../lib/styles.js'
import { cn } from '../lib/utils.js'

import { Button } from './button.js'
import { Icon } from './icon.js'

const TONES: Record<'ok' | 'warn' | 'bad' | 'neutro', { icon: LucideIcon; cls: string }> = {
  ok: { icon: CircleCheck, cls: 'text-good' },
  warn: { icon: TriangleAlert, cls: 'text-warn' },
  bad: { icon: OctagonAlert, cls: 'text-bad' },
  neutro: { icon: CircleHelp, cls: 'text-ink-soft' },
}

/** Monta una vez en la raíz; `viewportLabel` es el nombre de la región de avisos. */
export function ToastProvider({ viewportLabel, children }: { viewportLabel: string; children: React.ReactNode }) {
  return (
    <ToastPrimitive.Provider label={viewportLabel} swipeDirection="right">
      {children}
      <ToastPrimitive.Viewport className="fixed right-6 bottom-6 z-70 m-0 w-90 max-w-[calc(100vw-48px)] list-none p-0 outline-none" />
    </ToastPrimitive.Provider>
  )
}

export interface ToastProps extends Omit<React.ComponentPropsWithoutRef<typeof ToastPrimitive.Root>, 'type'> {
  tone?: keyof typeof TONES
  icon?: LucideIcon
  closeLabel: string
}

/** Sin barra de tiempo. Sin `duration` se queda hasta cerrarlo; hover y foco lo pausan (Radix). `bad` se anuncia como alerta. */
export function Toast({ tone = 'ok', icon, closeLabel, duration = Infinity, className, children, ...props }: ToastProps) {
  const t = TONES[tone]
  return (
    <ToastPrimitive.Root
      type={tone === 'bad' ? 'foreground' : 'background'}
      duration={duration}
      className={cn(
        raised,
        'flex items-center gap-2.5 py-2 pr-2 pl-3.5 text-ink data-[state=closed]:animate-[ap-toast-out_var(--exit)_var(--easing)_forwards] data-[state=open]:animate-[ap-entra_var(--base)_var(--easing)] motion-reduce:animate-none',
        className,
      )}
      {...props}
    >
      <span className={cn('flex', t.cls)}>
        <Icon icon={icon ?? t.icon} />
      </span>
      <ToastPrimitive.Description className="flex-1">{children}</ToastPrimitive.Description>
      <ToastPrimitive.Close asChild>
        <Button variant="ghost" size="sm" aria-label={closeLabel}>
          <Icon icon={X} />
        </Button>
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  )
}
