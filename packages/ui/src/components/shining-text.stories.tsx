import type { Meta, StoryObj } from '@storybook/react'

import { ShiningText } from './shining-text.js'

const meta: Meta<typeof ShiningText> = {
  title: 'Feedback/ShiningText',
  component: ShiningText,
  args: { text: 'El agente está redactando la contraoferta…' },
}

export default meta
type Story = StoryObj<typeof ShiningText>

export const Negotiation: Story = {}

export const Mission: Story = {
  args: { text: 'Buscando ofertas en 2 plataformas…' },
}

export const Intake: Story = {
  args: { text: 'Analizando el CSV financiero…' },
}

export const Chinese: Story = {
  args: { text: '代理正在起草还价…' },
}
