import * as MenuPrimitive from '@radix-ui/react-dropdown-menu'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { raised } from '../lib/styles.js'
import { cn } from '../lib/utils.js'

import { Icon } from './icon.js'

export const DropdownMenu = MenuPrimitive.Root
export const DropdownMenuTrigger = MenuPrimitive.Trigger

export const DropdownMenuContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof MenuPrimitive.Content>
>(({ className, sideOffset = 4, align = 'end', ...props }, ref) => (
  <MenuPrimitive.Portal>
    <MenuPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      align={align}
      className={cn(
        raised,
        'z-60 min-w-45 py-1 data-[state=closed]:animate-[ap-out_var(--exit)_var(--easing)_forwards] data-[state=open]:animate-[ap-persiana_var(--fast)_var(--easing-move)] motion-reduce:animate-none',
        className,
      )}
      {...props}
    />
  </MenuPrimitive.Portal>
))
DropdownMenuContent.displayName = 'DropdownMenuContent'

export interface DropdownMenuItemProps extends React.ComponentPropsWithoutRef<typeof MenuPrimitive.Item> {
  icon?: LucideIcon
  /** Acción destructiva: texto en `bad`. */
  danger?: boolean
}

/** Nivel 0 de movimiento: sin transición al entrar. */
export const DropdownMenuItem = React.forwardRef<HTMLDivElement, DropdownMenuItemProps>(
  ({ icon, danger, className, children, ...props }, ref) => (
    <MenuPrimitive.Item
      ref={ref}
      className={cn(
        'flex min-h-9 w-full cursor-pointer items-center gap-2.5 px-3 text-left whitespace-nowrap outline-none data-highlighted:bg-line data-disabled:cursor-not-allowed data-disabled:text-ink-muted',
        danger ? 'text-bad' : 'text-ink',
        className,
      )}
      {...props}
    >
      {icon && <Icon icon={icon} />}
      {children}
    </MenuPrimitive.Item>
  ),
)
DropdownMenuItem.displayName = 'DropdownMenuItem'
