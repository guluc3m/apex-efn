import type { Meta, StoryObj } from '@storybook/react'

import { ShiningText } from './shining-text.js'
import { SphereLoader } from './sphere-loader.js'

const meta = {
  title: 'Primitivas/Carga',
  component: SphereLoader,
  args: { label: 'Buscando ofertas…' },
} satisfies Meta<typeof SphereLoader>
export default meta
type Story = StoryObj<typeof meta>

export const Esferas: Story = {}
export const EsferasChino: Story = { args: { label: '正在搜索报价…' } }
export const TextoBrillante: Story = { render: () => <ShiningText>Pensando…</ShiningText> }
