import type { Meta, StoryObj } from '@storybook/react'

import { Skeleton } from './skeleton.js'

const meta = { title: 'Primitivas/Skeleton', component: Skeleton } satisfies Meta<typeof Skeleton>
export default meta
type Story = StoryObj<typeof meta>

/** Con la forma final del contenido, no un bloque genérico. */
export const FormaDeTabla: Story = {
  render: () => (
    <div className="flex flex-col gap-2.5" aria-busy="true">
      <Skeleton className="h-3.5 w-2/5" />
      <Skeleton className="h-3.5 w-11/12" />
      <Skeleton className="h-3.5 w-3/4" />
      <Skeleton className="h-3.5 w-5/6" />
    </div>
  ),
}
