import type { Meta, StoryObj } from '@storybook/react'

import { Toast, ToastProvider } from './toast.js'

const meta = { title: 'Primitivas/Toast', component: Toast } satisfies Meta
export default meta
type Story = StoryObj

export const Tonos: Story = {
  render: () => (
    <ToastProvider viewportLabel="Notificaciones">
      <Toast tone="ok" closeLabel="Cerrar" defaultOpen>
        Decisión firmada
      </Toast>
      <Toast tone="warn" closeLabel="Cerrar" defaultOpen>
        La sesión de firma caduca en 60 s
      </Toast>
      <Toast tone="bad" closeLabel="Cerrar" defaultOpen>
        No se pudo firmar
      </Toast>
    </ToastProvider>
  ),
}
