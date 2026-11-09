import type { Meta, StoryObj } from '@storybook/react'

import { Progress } from './progress.js'

const meta = {
  title: 'Primitivas/Progress',
  component: Progress,
  args: { value: 60, 'aria-label': 'Ofertas analizadas' },
} satisfies Meta<typeof Progress>
export default meta
type Story = StoryObj<typeof meta>

export const Acento: Story = {}
export const Aviso: Story = { args: { tone: 'warn', value: 85, 'aria-label': 'Presupuesto usado' } }
export const Peligro: Story = {
  args: { tone: 'bad', value: 100, 'aria-label': 'Presupuesto usado' },
}
