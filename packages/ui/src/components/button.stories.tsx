import type { Meta, StoryObj } from '@storybook/react'
import { PenLine } from 'lucide-react'

import { Button } from './button.js'
import { Icon } from './icon.js'

const meta = {
  title: 'Primitivas/Button',
  component: Button,
  args: { children: 'Continuar' },
} satisfies Meta<typeof Button>
export default meta
type Story = StoryObj<typeof meta>

export const Variantes: Story = {
  render: (args) => (
    <div className="flex flex-wrap items-center gap-3">
      {(['pri', 'sec', 'ghost', 'danger'] as const).map((variant) => (
        <Button key={variant} {...args} variant={variant}>
          {variant}
        </Button>
      ))}
    </div>
  ),
}
export const Tamanos: Story = {
  render: (args) => (
    <div className="flex items-center gap-3">
      {(['sm', 'md', 'lg'] as const).map((size) => (
        <Button key={size} {...args} size={size}>
          {size}
        </Button>
      ))}
    </div>
  ),
}
export const Firmar: Story = {
  args: {
    variant: 'pri',
    children: (
      <>
        <Icon icon={PenLine} />
        Firmar y comprar
      </>
    ),
  },
}
export const DeshabilitadoConMotivo: Story = {
  args: {
    disabledReason: 'Tu rol no permite firmar. Pídeselo a alguien con rol finanzas, admin u owner.',
    children: 'Seguir y comprar',
  },
}
export const Ocupado: Story = { args: { busy: true, children: 'Enviando…' } }
export const Chino: Story = { args: { variant: 'pri', children: '确认并签署' } }
