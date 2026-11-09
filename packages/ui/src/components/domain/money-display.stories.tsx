import type { Meta, StoryObj } from '@storybook/react'

import { MoneyDisplay } from './money-display.js'

const meta = {
  title: 'Dominio/MoneyDisplay',
  component: MoneyDisplay,
  args: { amountMinor: 1234567, currency: 'EUR', locale: 'es-ES' },
} satisfies Meta<typeof MoneyDisplay>
export default meta
type Story = StoryObj<typeof meta>

export const Euro: Story = {}
export const Grande: Story = { args: { size: 'large' } }
export const Negativo: Story = { args: { amountMinor: -482050 } }
export const Yuan: Story = { args: { amountMinor: 8800000, currency: 'CNY', locale: 'zh-CN' } }
export const Dolar: Story = { args: { amountMinor: 1240000, currency: 'USD', locale: 'en-US' } }
/** Por encima de 2^53: BigInt, sin pasar por coma flotante. */
export const ImporteEnorme: Story = { args: { amountMinor: 9007199254740993n } }
export const ConvertidoConOriginal: Story = {
  args: {
    amountMinor: 1139200,
    originalLabel: 'Importe original',
    original: { amountMinor: 1240000, currency: 'USD' },
  },
}
