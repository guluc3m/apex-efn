import * as TabsPrimitive from '@radix-ui/react-tabs'
import * as React from 'react'

import { cn } from '../lib/utils.js'

export const Tabs = TabsPrimitive.Root
export const TabsContent = TabsPrimitive.Content

/** El indicador de 2 px viaja a la pestaña activa: es la línea la que se mueve. La primera medida no anima. */
export const TabsList = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>>(
  ({ className, children, ...props }, forwarded) => {
    const list = React.useRef<HTMLDivElement | null>(null)
    const [bar, setBar] = React.useState({ x: 0, w: 0, ready: false })
    const measure = React.useCallback(() => {
      const el = list.current?.querySelector<HTMLElement>('[data-state="active"]')
      if (el) setBar((b) => ({ x: el.offsetLeft, w: el.offsetWidth, ready: b.w > 0 }))
    }, [])
    React.useLayoutEffect(() => {
      measure()
      const node = list.current
      if (!node) return
      const mo = new MutationObserver(measure)
      mo.observe(node, { attributes: true, attributeFilter: ['data-state'], subtree: true })
      const ro = new ResizeObserver(measure)
      ro.observe(node)
      return () => {
        mo.disconnect()
        ro.disconnect()
      }
    }, [measure])
    return (
      <TabsPrimitive.List
        ref={(n) => {
          list.current = n
          if (typeof forwarded === 'function') forwarded(n)
          else if (forwarded) forwarded.current = n
        }}
        className={cn('relative flex flex-wrap gap-1 border-b border-line', className)}
        {...props}
      >
        {children}
        <span
          aria-hidden="true"
          data-ready={bar.ready}
          // ponytail: posición medida en runtime, no hay clase estática equivalente.
          style={{ width: bar.w, transform: `translateX(${bar.x}px)`, opacity: bar.w ? 1 : 0 }}
          className="pointer-events-none absolute bottom-0 left-0 h-0.5 bg-accent data-[ready=true]:transition-[transform,width] data-[ready=true]:duration-(--base) data-[ready=true]:ease-apex-move motion-reduce:transition-none"
        />
      </TabsPrimitive.List>
    )
  },
)
TabsList.displayName = 'TabsList'

export const TabsTrigger = React.forwardRef<HTMLButtonElement, React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>>(
  ({ className, ...props }, ref) => (
    <TabsPrimitive.Trigger
      ref={ref}
      className={cn(
        'inline-flex min-h-9 cursor-pointer items-center gap-1.5 px-3 font-medium text-ink-soft transition-[color] duration-(--fast) ease-apex hover:text-ink data-[state=active]:text-ink',
        className,
      )}
      {...props}
    />
  ),
)
TabsTrigger.displayName = 'TabsTrigger'
