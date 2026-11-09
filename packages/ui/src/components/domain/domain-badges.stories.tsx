import type { Meta, StoryObj } from '@storybook/react'

import { ConfidenceBandBadge, type ConfidenceBand } from './confidence-band-badge.js'
import { FinancialVerdictBadge, type FinancialVerdict } from './financial-verdict-badge.js'
import { PriceBandBadge, type PriceBand } from './price-band-badge.js'
import { SignatureStatusBadge, type SignatureStatus } from './signature-status-badge.js'

const meta = { title: 'Dominio/Badges' } satisfies Meta
export default meta
type Story = StoryObj

const PRICE: Record<PriceBand, string> = {
  normal: 'Precio normal',
  atypical: 'Precio atípico',
  implausible: 'Precio implausible',
  insufficient_reference: 'Sin referencia',
}
const CONFIDENCE: Record<ConfidenceBand, string> = {
  high: 'Confianza alta · 91',
  medium: 'Confianza media · 63',
  low: 'Confianza baja · 38',
  untrusted: 'No fiable · 12',
  insufficient_data: 'Sin datos suficientes',
}
const VERDICT: Record<FinancialVerdict, string> = {
  within_budget: 'En presupuesto',
  stretch: 'Al límite',
  out_of_budget: 'Fuera de presupuesto',
}
const SIGNATURE: Record<SignatureStatus, string> = {
  signed: 'Firmado',
  pending: 'Pendiente',
  invalid: 'Firma inválida',
}

function Row({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-ink-muted m-0 text-[13px] font-medium">{title}</h3>
      <div className="flex flex-wrap gap-3">{children}</div>
    </section>
  )
}

/** Todos los valores de DESIGN §6, en el orden de la fila de oferta: banda · confianza · veredicto · firma. */
export const TodosLosValores: Story = {
  render: () => (
    <div className="flex flex-col gap-5">
      <Row title="Banda de precio">
        {(Object.keys(PRICE) as PriceBand[]).map((b) => (
          <PriceBandBadge key={b} band={b} label={PRICE[b]} />
        ))}
      </Row>
      <Row title="Confianza del vendedor">
        {(Object.keys(CONFIDENCE) as ConfidenceBand[]).map((b) => (
          <ConfidenceBandBadge key={b} band={b} label={CONFIDENCE[b]} />
        ))}
      </Row>
      <Row title="Veredicto financiero">
        {(Object.keys(VERDICT) as FinancialVerdict[]).map((v) => (
          <FinancialVerdictBadge key={v} verdict={v} label={VERDICT[v]} />
        ))}
      </Row>
      <Row title="Firma">
        {(Object.keys(SIGNATURE) as SignatureStatus[]).map((s) => (
          <SignatureStatusBadge key={s} status={s} label={SIGNATURE[s]} />
        ))}
      </Row>
    </div>
  ),
}

/** El badge abre un popover con el porqué: señales y `model_version` en mono. */
export const ConDesglose: Story = {
  render: () => (
    <ConfidenceBandBadge
      band="medium"
      label="Confianza media · 63"
      breakdownTitle="Por qué esta confianza"
      breakdown={
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-ink-muted">Antigüedad</dt>
          <dd className="m-0">900 días</dd>
          <dt className="text-ink-muted">Ventas</dt>
          <dd className="m-0">640 ventas · 21 % repetición</dd>
          <dt className="text-ink-muted">Reseñas</dt>
          <dd className="m-0">4,4 de 88 · 62 % verificadas</dd>
          <dt className="text-ink-muted">Modelo</dt>
          <dd className="m-0 font-mono">trust-v1</dd>
        </dl>
      }
    />
  ),
}

export const Chino: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3">
      <PriceBandBadge band="atypical" label="价格异常" />
      <ConfidenceBandBadge band="low" label="可信度低 · 38" />
      <FinancialVerdictBadge verdict="stretch" label="接近预算上限" />
      <SignatureStatusBadge status="signed" label="已签署" />
    </div>
  ),
}
