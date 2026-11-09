import type { Meta, StoryObj } from '@storybook/react'

import {
  SigningSessionIndicator,
  type SigningSessionIndicatorProps,
} from './signing-session-indicator.js'

const labels: SigningSessionIndicatorProps['labels'] = {
  signing: 'Firmas',
  noSession: 'Sin sesión de firma',
  expiring: 'Caduca pronto',
  expired: 'Sesión caducada',
  exhausted: 'Sin firmas disponibles',
  openSession: 'Abrir sesión de firma',
  reauth: 'Reautenticar para firmar',
  timerLabel: (time) => `La sesión caduca en ${time}`,
}

/** `now` se inyecta: el estado no depende del reloj real. */
const NOW = Date.UTC(2026, 10, 9, 12, 0, 0)
const base = {
  labels,
  action: { href: '/firma' },
  now: NOW,
  signer: 'Laura Gómez',
} satisfies Partial<SigningSessionIndicatorProps>

const meta = {
  title: 'Compuestos/SigningSessionIndicator',
  component: SigningSessionIndicator,
  args: base,
} satisfies Meta<typeof SigningSessionIndicator>
export default meta
type Story = StoryObj<typeof meta>

export const Activa: Story = {
  args: { expiresAt: NOW + 12 * 60_000, signaturesLeft: 8, signaturesLabel: '8 firmas restantes' },
}
export const CaducaPronto: Story = {
  args: { expiresAt: NOW + 45_000, signaturesLeft: 3, signaturesLabel: '3 firmas restantes' },
}
export const Caducada: Story = { args: { expiresAt: NOW - 1000 } }
export const SinFirmas: Story = {
  args: { expiresAt: NOW + 5 * 60_000, signaturesLeft: 0, signaturesLabel: '0 firmas restantes' },
}
export const SinSesion: Story = { args: { expiresAt: undefined, signer: undefined } }
