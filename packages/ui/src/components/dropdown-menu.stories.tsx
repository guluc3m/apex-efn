import type { Meta, StoryObj } from '@storybook/react'
import { Pause, Trash2 } from 'lucide-react'

import { Button } from './button.js'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './dropdown-menu.js'

const meta = { title: 'Primitivas/DropdownMenu', component: DropdownMenu } satisfies Meta<
  typeof DropdownMenu
>
export default meta
type Story = StoryObj<typeof meta>

export const Acciones: Story = {
  render: () => (
    <DropdownMenu defaultOpen>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" aria-label="Más acciones">
          ⋯
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem icon={Pause}>Aparcar</DropdownMenuItem>
        <DropdownMenuItem icon={Trash2} danger>
          Descartar
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  ),
}
