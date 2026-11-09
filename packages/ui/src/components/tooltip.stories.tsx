import type { Meta, StoryObj } from '@storybook/react'

import { Button } from './button.js'
import { Tooltip } from './tooltip.js'

const meta = { title: 'Primitivas/Tooltip', component: Tooltip } satisfies Meta
export default meta
type Story = StoryObj

export const Base: Story = {
  render: () => (
    <Tooltip text="Importe original: 12.400,00 USD">
      <Button variant="sec">Ver original</Button>
    </Tooltip>
  ),
}
