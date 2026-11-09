import type { Meta, StoryObj } from '@storybook/react'
import { Gavel, Target } from 'lucide-react'

import { Logo } from '../logo.js'

import { AppHeader } from './app-header.js'
import { CompanyNav } from './company-nav.js'

const items = [
  { label: 'Decisiones', href: '/decisiones', icon: Gavel, current: true },
  { label: 'Misiones', href: '/misiones', icon: Target },
]

const meta = { title: 'Compuestos/Cabecera' } satisfies Meta
export default meta
type Story = StoryObj

export const Cabecera: Story = {
  render: () => (
    <AppHeader
      navLabel="Navegación principal"
      skipLabel="Saltar al contenido"
      items={items}
      brand={<Logo href="/" size="sm" />}
      signOut={{ label: 'Cerrar sesión', href: '/salir' }}
    />
  ),
}
export const NavegacionDeEmpresa: Story = {
  render: () => <CompanyNav label="Empresa" items={items} />,
}
