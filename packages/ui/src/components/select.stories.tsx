import type { Meta, StoryObj } from '@storybook/react'

import { Select } from './select.js'

const options = [
  { value: 'EUR', label: 'Euro (EUR)' },
  { value: 'USD', label: 'Dólar (USD)' },
  { value: 'CNY', label: 'Yuan (CNY)' },
]
const meta = {
  title: 'Primitivas/Select',
  component: Select,
  args: { label: 'Divisa base', options, defaultValue: 'EUR' },
} satisfies Meta<typeof Select>
export default meta
type Story = StoryObj<typeof meta>

export const Base: Story = {}
export const SinValor: Story = {
  args: { defaultValue: undefined, placeholder: 'Elige una divisa' },
}
export const EtiquetaOculta: Story = { args: { hideLabel: true } }
export const Deshabilitado: Story = { args: { disabled: true } }
