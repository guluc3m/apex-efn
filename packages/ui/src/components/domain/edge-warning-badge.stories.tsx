import type { Meta, StoryObj } from '@storybook/react'

import { EdgeWarningBadge } from './edge-warning-badge.js'

const meta = { title: 'Dominio/EdgeWarningBadge' } satisfies Meta
export default meta
type Story = StoryObj

export const Avisos: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3">
      <EdgeWarningBadge kind="fx_provisional" label="Tipo de cambio provisional" />
      <EdgeWarningBadge kind="financials_stale" label="Datos financieros caducados" />
      <EdgeWarningBadge kind="live_connection_lost" label="Sin conexión en vivo" />
    </div>
  ),
}
export const ConExplicacion: Story = {
  render: () => (
    <EdgeWarningBadge
      kind="fx_provisional"
      label="Tipo de cambio provisional"
      explanationTitle="Por qué es provisional"
      explanation="El importe en EUR usa una tasa del 06/11, con más de 36 h."
    />
  ),
}
