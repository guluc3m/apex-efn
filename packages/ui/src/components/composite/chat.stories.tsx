import type { Meta, StoryObj } from '@storybook/react'

import { Chat, type ChatMessage } from './chat.js'
import { Thinking } from './thinking.js'

const labels = {
  input: 'Mensaje',
  placeholder: 'Escribe un mensaje…',
  send: 'Enviar',
  stop: 'Detener',
  attach: 'Adjuntar',
  hint: 'Intro para enviar',
}
const messages: ChatMessage[] = [
  {
    id: '1',
    role: 'agent',
    author: 'Agente',
    text: 'Buenos días, ¿podemos hablar de precio por volumen para 3.000 m?',
    time: '12:04',
  },
  {
    id: '2',
    role: 'seller',
    author: 'Vendedor C',
    text: 'Con 3.000 m puedo ofrecer un 4 % de descuento.',
    time: '12:06',
  },
  {
    id: '3',
    role: 'human',
    author: 'Laura Gómez',
    text: 'Pídele el 7 % si cerramos marco anual.',
    time: '12:08',
  },
]

const meta = {
  title: 'Compuestos/Chat',
  component: Chat,
  args: { labels, onSend: () => {} },
} satisfies Meta<typeof Chat>
export default meta
type Story = StoryObj<typeof meta>

export const Reposo: Story = {}
export const Conversacion: Story = { args: { messages } }
export const Pensando: Story = {
  args: {
    messages,
    thinking: true,
    phrases: ['Revisando la contraoferta…', 'Comprobando el límite de descuento…'],
  },
}
export const Bloqueado: Story = {
  args: { messages, disabledReason: 'Un humano tiene el control de esta negociación.' },
}
export const Chino: Story = {
  args: {
    labels: { input: '消息', placeholder: '输入消息…', send: '发送', stop: '停止' },
    messages: [
      {
        id: '1',
        role: 'seller',
        author: '卖家 C',
        text: '3000米可以给您4%的折扣。',
        time: '12:06',
      },
    ],
  },
}
export const SoloPensando: StoryObj<typeof Thinking> = {
  render: () => <Thinking phrases={['Analizando ofertas…', 'Filtrando precios anómalos…']} />,
}
