import type { Meta, StoryObj } from '@storybook/react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs.js'

const meta = { title: 'Primitivas/Tabs', component: Tabs } satisfies Meta<typeof Tabs>
export default meta
type Story = StoryObj<typeof meta>

export const Base: Story = {
  render: () => (
    <Tabs defaultValue="ofertas">
      <TabsList aria-label="Secciones de la misión">
        <TabsTrigger value="ofertas">Ofertas</TabsTrigger>
        <TabsTrigger value="negociacion">Negociación</TabsTrigger>
        <TabsTrigger value="auditoria">Auditoría</TabsTrigger>
      </TabsList>
      <TabsContent value="ofertas" className="pt-4">
        11 ofertas de 3 plataformas.
      </TabsContent>
      <TabsContent value="negociacion" className="pt-4">
        2 conversaciones activas.
      </TabsContent>
      <TabsContent value="auditoria" className="pt-4">
        Cadena verificada.
      </TabsContent>
    </Tabs>
  ),
}
