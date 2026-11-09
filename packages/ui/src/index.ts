/**
 * @apex/ui
 *
 * Sistema de diseño de APEX-EFN (packages/ui/DESIGN.md) sobre Radix + Tailwind v4.
 * Los textos llegan por props: este paquete no usa next-intl.
 */

export { cn } from './lib/utils.js'

export { Button, buttonVariants, type ButtonProps } from './components/button.js'
export { Badge, type BadgeProps } from './components/badge.js'
export { Icon, type IconProps } from './components/icon.js'
export { Logo, type LogoProps } from './components/logo.js'
export { ShiningText, shiningClass } from './components/shining-text.js'
export { SphereLoader, type SphereLoaderProps } from './components/sphere-loader.js'
export { Tooltip, type TooltipProps } from './components/tooltip.js'
export { Popover, PopoverContent, PopoverTrigger, type PopoverContentProps } from './components/popover.js'
export { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, type DropdownMenuItemProps } from './components/dropdown-menu.js'
export { Select, type SelectOption, type SelectProps } from './components/select.js'
export { Tabs, TabsContent, TabsList, TabsTrigger } from './components/tabs.js'
export { Dialog, DialogClose, DialogContent, DialogTrigger, type DialogContentProps } from './components/dialog.js'
export { Toast, ToastProvider, type ToastProps } from './components/toast.js'
export { Input, type InputProps } from './components/input.js'
export { Label } from './components/label.js'
export { Progress } from './components/progress.js'
export { Skeleton } from './components/skeleton.js'

// Los siguientes agentes añaden aquí sus componentes sin tocar este archivo.
export * from './components/domain/index.js'
export * from './components/composite/index.js'
