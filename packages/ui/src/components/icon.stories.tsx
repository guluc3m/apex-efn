import type { Meta, StoryObj } from '@storybook/react'
import { Inbox, Lock } from 'lucide-react'

import { Icon } from './icon.js'

const meta = { title: 'Primitivas/Icon', component: Icon, args: { icon: Inbox } } satisfies Meta<
  typeof Icon
>
export default meta
type Story = StoryObj<typeof meta>

export const Decorativo: Story = {}
export const ConEtiqueta: Story = { args: { icon: Lock, label: 'Solo lectura', size: 20 } }
