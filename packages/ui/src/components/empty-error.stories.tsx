import type { Meta, StoryObj } from '@storybook/react'
import { Eye, Inbox, Lock, Plus, SearchX } from 'lucide-react'

import { Button } from './button.js'
import { EmptyState } from './empty-state.js'
import { ErrorState } from './error-state.js'
import { Icon } from './icon.js'

const meta = { title: 'Estados/Vacío y error' } satisfies Meta
export default meta
type Story = StoryObj

export const ColaVacia: Story = {
  render: () => (
    <EmptyState
      icon={Inbox}
      title="No tienes nada pendiente"
      description="Las ofertas que necesiten tu firma aparecerán aquí."
      actions={<Button>Ver misiones en curso</Button>}
    />
  ),
}
export const MisionSinOfertasValidas: Story = {
  render: () => (
    <EmptyState
      icon={SearchX}
      title="Ninguna de las 11 ofertas pasa los filtros"
      description="7 por precio implausible, 3 por vendedor no fiable, 1 sin certificación CE."
      actions={
        <>
          <Button>
            <Icon icon={Eye} />
            Ver las descartadas
          </Button>
          <Button>
            <Icon icon={Plus} />
            Ampliar plataformas
          </Button>
        </>
      }
    />
  ),
}
export const SoloLectura: Story = {
  render: () => (
    <EmptyState
      icon={Lock}
      title="Tu rol es de solo lectura"
      description="Pide a un responsable que decida."
    />
  ),
}
export const ErrorDelServidor: Story = {
  render: () => (
    <ErrorState
      title="No se ha podido cargar la cola"
      detail="El servidor no responde. No se ha firmado ni cambiado nada."
      retryLabel="Reintentar"
      onRetry={() => {}}
      trace="trace 4f2a91c0"
    />
  ),
}
export const ErrorSinReintento: Story = {
  render: () => <ErrorState title="No tienes permiso para ver esta misión" />,
}
export const Chino: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <EmptyState
        icon={Inbox}
        title="没有待处理的事项"
        description="需要您签署的报价会显示在这里。"
      />
      <ErrorState
        title="无法加载队列"
        detail="服务器无响应。未签署或更改任何内容。"
        retryLabel="重试"
        onRetry={() => {}}
      />
    </div>
  ),
}
