import type { Meta, StoryObj } from '@storybook/react'

import { ConfidenceBandBadge } from '../domain/confidence-band-badge.js'
import { MoneyDisplay } from '../domain/money-display.js'

import { Table, type TableColumn } from './table.js'

interface Row {
  id: string
  item: string
  seller: string
  minor: number
  score: number
  band: 'high' | 'medium' | 'low'
}

const rows: Row[] = [
  {
    id: 'c',
    item: 'Cable apantallado · 3.000 m',
    seller: 'Vendedor C',
    minor: 2826000,
    score: 71,
    band: 'medium',
  },
  {
    id: 'b',
    item: 'Válvula de bola DN25 · 800 ud',
    seller: 'Vendedor B',
    minor: 1203200,
    score: 38,
    band: 'low',
  },
  {
    id: 'e',
    item: 'Motor trifásico 4 kW · 60 ud',
    seller: 'Vendedor E',
    minor: 1714000,
    score: 91,
    band: 'high',
  },
]

const columns: TableColumn<Row>[] = [
  { id: 'item', header: 'Elemento', sortValue: (r) => r.item, cell: (r) => r.item },
  {
    id: 'amount',
    header: 'Importe',
    num: true,
    sortValue: (r) => r.minor,
    cell: (r) => <MoneyDisplay amountMinor={r.minor} currency="EUR" locale="es-ES" />,
  },
  {
    id: 'conf',
    header: 'Confianza',
    sortable: false,
    cell: (r) => <ConfidenceBandBadge band={r.band} label={`${r.band} · ${r.score}`} />,
  },
]

const meta = {
  title: 'Compuestos/Table',
  component: Table<Row>,
  args: {
    columns,
    rows,
    getRowId: (r: Row) => r.id,
    getHref: (r: Row) => `/decisiones/${r.id}`,
    caption: 'Elementos pendientes en la cola',
    empty: 'Sin elementos',
  },
} satisfies Meta<typeof Table<Row>>
export default meta
type Story = StoryObj<typeof meta>

export const Datos: Story = {}
export const OrdenadaPorImporte: Story = {
  args: { defaultSorting: [{ id: 'amount', desc: true }] },
}
export const Cargando: Story = { args: { loading: true } }
export const Vacia: Story = { args: { rows: [], empty: 'No tienes nada pendiente' } }
export const Densa: Story = { args: { dense: true } }
export const Paginada: Story = { args: { pageSize: 2, loadMoreLabel: 'Cargar más' } }
