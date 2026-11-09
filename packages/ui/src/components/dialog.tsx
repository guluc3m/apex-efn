import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import * as React from 'react'

import { raised } from '../lib/styles.js'
import { cn } from '../lib/utils.js'

import { Button } from './button.js'
import { Icon } from './icon.js'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export interface DialogContentProps extends Omit<React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>, 'title'> {
  title: string
  description?: string
  /** Texto del botón X (llega por props, este paquete no traduce). */
  closeLabel: string
}

/** Modal: foco atrapado, Escape y X cierran. Sin cierre por clic en el fondo, porque aquí se firma. */
export const DialogContent = React.forwardRef<HTMLDivElement, DialogContentProps>(
  ({ title, description, closeLabel, className, children, ...props }, ref) => (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-100 bg-bg/70 data-[state=closed]:animate-[ap-out_var(--exit)_var(--easing)_forwards] data-[state=open]:animate-[ap-in_var(--fast)_var(--easing)] motion-reduce:animate-none" />
      <DialogPrimitive.Content
        ref={ref}
        onInteractOutside={(e) => e.preventDefault()}
        {...(description ? {} : { 'aria-describedby': undefined })}
        className={cn(
          raised,
          'fixed top-1/2 left-1/2 z-100 box-border w-[calc(100%-64px)] max-w-140 -translate-x-1/2 -translate-y-1/2 p-6 text-ink outline-none data-[state=closed]:animate-[ap-out_var(--exit)_var(--easing)_forwards] data-[state=open]:animate-[ap-dlg_var(--overlay)_var(--easing)] motion-reduce:animate-none',
          className,
        )}
        {...props}
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <DialogPrimitive.Title className="m-0 text-[17px] leading-[1.35] font-semibold tracking-[-0.01em]">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close asChild>
            <Button variant="ghost" size="sm" aria-label={closeLabel}>
              <Icon icon={X} />
            </Button>
          </DialogPrimitive.Close>
        </div>
        {description && <DialogPrimitive.Description className="m-0 mb-4 text-ink-soft">{description}</DialogPrimitive.Description>}
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  ),
)
DialogContent.displayName = 'DialogContent'
