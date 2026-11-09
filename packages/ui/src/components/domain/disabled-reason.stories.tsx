import type { Meta, StoryObj } from '@storybook/react'
import { PenLine } from 'lucide-react'

import { Button } from '../button.js'
import { Icon } from '../icon.js'

import { DisabledReason } from './disabled-reason.js'

const meta = { title: 'Dominio/DisabledReason', component: DisabledReason } satisfies Meta<
  typeof DisabledReason
>
export default meta
type Story = StoryObj<typeof meta>

const action = (
  <Button variant="sec">
    <Icon icon={PenLine} />
    Seguir y comprar
  </Button>
)

/** El motivo lo devuelve la API (criterio 16); el botón sigue enfocable. */
export const Bloqueado: Story = {
  args: {
    reason: 'Los datos financieros han caducado. Reimporta el CSV para comprar.',
    children: action,
  },
}
export const SinMotivo: Story = { args: { children: action } }
