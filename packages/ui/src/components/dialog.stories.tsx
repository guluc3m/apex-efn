import type { Meta, StoryObj } from '@storybook/react'

import { Button } from './button.js'
import { Dialog, DialogClose, DialogContent, DialogTrigger } from './dialog.js'

const meta = { title: 'Primitivas/Dialog', component: Dialog } satisfies Meta<typeof Dialog>
export default meta
type Story = StoryObj<typeof meta>

/** No cierra al hacer clic fuera: aquí se firma (DESIGN §6). */
export const Descartar: Story = {
  render: () => (
    <Dialog defaultOpen>
      <DialogTrigger asChild>
        <Button>Descartar oferta</Button>
      </DialogTrigger>
      <DialogContent
        title="Descartar oferta"
        description="La decisión queda firmada y registrada en la cadena de auditoría."
        closeLabel="Cerrar"
      >
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button>Cancelar</Button>
          </DialogClose>
          <Button variant="danger">Descartar</Button>
        </div>
      </DialogContent>
    </Dialog>
  ),
}
export const Chino: Story = {
  render: () => (
    <Dialog defaultOpen>
      <DialogContent
        title="放弃报价"
        description="该决定将被签署并记录在审计链中。"
        closeLabel="关闭"
      >
        <DialogClose asChild>
          <Button>取消</Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  ),
}
