import type { Meta, StoryObj } from '@storybook/react'

import { Button } from './button.js'
import { Popover, PopoverContent, PopoverTrigger } from './popover.js'

const meta = { title: 'Primitivas/Popover', component: Popover } satisfies Meta<typeof Popover>
export default meta
type Story = StoryObj<typeof meta>

export const Base: Story = {
  render: () => (
    <Popover>
      <PopoverTrigger asChild>
        <Button>Por qué esta banda</Button>
      </PopoverTrigger>
      <PopoverContent title="Por qué esta banda">
        Mediana de referencia 41,20 € sobre 23 ofertas.
      </PopoverContent>
    </Popover>
  ),
}
export const Abierto: Story = {
  render: () => (
    <Popover defaultOpen>
      <PopoverTrigger asChild>
        <Button>Por qué esta banda</Button>
      </PopoverTrigger>
      <PopoverContent title="Por qué esta banda">
        Mediana de referencia 41,20 € sobre 23 ofertas.
      </PopoverContent>
    </Popover>
  ),
}
