import type { Meta, StoryObj } from '@storybook/react'

import { Input } from './input.js'
import { Label } from './label.js'

const meta = { title: 'Primitivas/Input', component: Input } satisfies Meta<typeof Input>
export default meta
type Story = StoryObj<typeof meta>

/** Importes: texto decimal con divisa explícita, nunca `type="number"` (DESIGN §6). */
export const ConEtiqueta: Story = {
  render: () => (
    <div className="flex max-w-80 flex-col gap-1">
      <Label htmlFor="imp">Presupuesto máximo (EUR)</Label>
      <Input id="imp" inputMode="decimal" placeholder="0,00" />
    </div>
  ),
}
export const Deshabilitado: Story = {
  args: { 'aria-label': 'Empresa', value: 'Industrias Norte S.L.', disabled: true, readOnly: true },
}
export const Chino: Story = {
  render: () => (
    <div className="flex max-w-80 flex-col gap-1">
      <Label htmlFor="cn">公司名称</Label>
      <Input id="cn" defaultValue="北方工业有限公司" />
    </div>
  ),
}
