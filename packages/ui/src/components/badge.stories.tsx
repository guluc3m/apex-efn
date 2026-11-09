import type { Meta, StoryObj } from '@storybook/react'

import { Badge } from './badge.js'

const meta = { title: 'Primitivas/Badge', component: Badge } satisfies Meta<typeof Badge>
export default meta
type Story = StoryObj<typeof meta>

/** La forma del icono distingue el tono además del color (DESIGN §4). */
export const Tonos: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3">
      <Badge tone="ok">En presupuesto</Badge>
      <Badge tone="warn">Al límite</Badge>
      <Badge tone="bad">Fuera de presupuesto</Badge>
      <Badge tone="neutro">Sin datos suficientes</Badge>
      <Badge tone="plano">Borrador</Badge>
    </div>
  ),
}
export const Chino: Story = { render: () => <Badge tone="warn">汇率为临时值</Badge> }
