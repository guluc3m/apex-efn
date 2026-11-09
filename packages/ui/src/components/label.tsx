import * as LabelPrimitive from '@radix-ui/react-label'
import * as React from 'react'

import { cn } from '../lib/utils.js'

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root ref={ref} className={cn('text-[13px] leading-[1.45] text-ink-muted', className)} {...props} />
))
Label.displayName = 'Label'

export { Label }
