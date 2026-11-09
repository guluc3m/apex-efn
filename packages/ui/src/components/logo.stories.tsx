import type { Meta, StoryObj } from '@storybook/react'

import { Logo } from './logo.js'

const meta = { title: 'Primitivas/Logo', component: Logo } satisfies Meta<typeof Logo>
export default meta
type Story = StoryObj<typeof meta>

export const Tamanos: Story = {
  render: () => (
    <div className="flex items-end gap-8">
      {(['sm', 'md', 'lg'] as const).map((size) => (
        <Logo key={size} size={size} />
      ))}
    </div>
  ),
}
export const Isotipo: Story = { args: { variant: 'isotipo', size: 'md' } }
export const ConEnlace: Story = { args: { href: '/', size: 'md' } }
export const Suave: Story = { args: { tone: 'soft' } }
