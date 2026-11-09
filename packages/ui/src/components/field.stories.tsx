import type { Meta, StoryObj } from '@storybook/react'

import { Checkbox } from './checkbox.js'
import { Field } from './field.js'
import { Input } from './input.js'
import { MoneyInput } from './money-input.js'

const meta = { title: 'Formularios/Campos' } satisfies Meta
export default meta
type Story = StoryObj

export const ConAyuda: Story = {
  render: () => (
    <Field label="NIF / CIF" hint="Tal como aparece en tu factura." className="max-w-80">
      {(c) => <Input {...c} defaultValue="B12345678" />}
    </Field>
  ),
}
export const ConError: Story = {
  render: () => (
    <Field
      label="NIF / CIF"
      hint="Tal como aparece en tu factura."
      error="El formato del NIF no es válido."
      className="max-w-80"
    >
      {(c) => <Input {...c} defaultValue="B123" />}
    </Field>
  ),
}
export const Importe: Story = {
  render: () => (
    <Field label="Presupuesto máximo" hint="Importe con decimales." className="max-w-80">
      {(c) => <MoneyInput {...c} currency="EUR" placeholder="0,00" />}
    </Field>
  ),
}
export const Casillas: Story = {
  render: () => (
    <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
      <legend className="text-ink-muted mb-2 p-0 text-[13px]">Plataformas</legend>
      <Checkbox label="Plataforma A" defaultChecked />
      <Checkbox label="Plataforma B" />
      <Checkbox label="Plataforma C (desactivada)" disabled />
    </fieldset>
  ),
}
export const Chino: Story = {
  render: () => (
    <Field label="最高预算" hint="请输入含小数的金额。" className="max-w-80">
      {(c) => <MoneyInput {...c} currency="CNY" />}
    </Field>
  ),
}
