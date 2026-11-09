import * as PopoverPrimitive from '@radix-ui/react-popover'
import * as React from 'react'

import { raised } from '../lib/styles.js'
import { cn } from '../lib/utils.js'

export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger

export interface PopoverContentProps extends React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content> {
  /** Título visible y nombre accesible del diálogo. */
  title?: string
}

/** No modal: Escape cierra y devuelve el foco al gatillo. */
export const PopoverContent = React.forwardRef<HTMLDivElement, PopoverContentProps>(
  ({ title, className, children, sideOffset = 6, align = 'start', ...props }, ref) => (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        align={align}
        aria-label={title}
        className={cn(
          raised,
          'z-60 w-75 px-4 py-3 text-ink data-[state=closed]:animate-[ap-out_var(--exit)_var(--easing)_forwards] data-[state=open]:animate-[ap-persiana_var(--fast)_var(--easing-move)] motion-reduce:animate-none',
          className,
        )}
        {...props}
      >
        {title && <strong className="mb-1 block font-semibold">{title}</strong>}
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  ),
)
PopoverContent.displayName = 'PopoverContent'
