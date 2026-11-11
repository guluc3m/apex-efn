'use client'

import type { Deal } from '@apex/shared-types/contracts'
import { Button, Icon, MoneyDisplay, Select, Tabs, TabsList, TabsTrigger } from '@apex/ui'
import { ChevronLeft, Handshake, ListTodo, ScrollText } from 'lucide-react'
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useEffect } from 'react'

import { AppLink } from '@/components/app-link'
import { useQueryClient } from '@tanstack/react-query'

import { queryKeys, subscribeMissionEvents, useDeals, useGateQueue, useNegotiationMessages } from '@/lib/api'
import { remaining } from '@/lib/decisions'

import { DealBadges } from './deal-badges'
import { DealDetail } from './deal-detail'
import { KpiStrip } from './kpi-strip'

type FilterKey = 'precio' | 'confianza' | 'veredicto' | 'plataforma' | 'firma'
const FILTERS: { key: FilterKey; label: string; ns?: string; values: string[]; param: string }[] = [
  { key: 'precio', label: 'price', ns: 'band', values: ['normal', 'atypical', 'implausible', 'insufficient_reference'], param: 'price_band' },
  { key: 'confianza', label: 'confidence', ns: 'conf', values: ['high', 'medium', 'low', 'untrusted', 'insufficient_data'], param: 'confidence_band' },
  { key: 'veredicto', label: 'verdict', ns: 'verdict', values: ['within_budget', 'stretch', 'out_of_budget'], param: 'financial_verdict' },
  { key: 'plataforma', label: 'platform', values: [], param: 'platform' },
  { key: 'firma', label: 'signature', ns: 'sig', values: ['unsigned', 'pending', 'signed', 'invalid'], param: 'signature_status' },
]

/** Maestro-detalle. El trato y la pestaña van a la URL con push; los filtros con replace (#141). Filtra el servidor. */
export function DecisionsView({ role }: { role: string }) {
  const t = useTranslations('decisions')
  const tg = useTranslations('gate')
  const locale = useLocale()
  const router = useRouter()
  const pathname = usePathname()
  const query = useSearchParams()
  const { dealId } = useParams<{ dealId?: string }>()
  const inTranscript = pathname.endsWith('/transcripcion')

  const view = query.get('vista') === 'tratos' ? 'tratos' : 'cola'
  const go = (path: string, params: URLSearchParams, mode: 'push' | 'replace') => {
    const qs = params.toString()
    router[mode](`/${locale}${path}${qs ? `?${qs}` : ''}` as never)
  }
  const withParam = (k: string, v: string | null) => {
    const p = new URLSearchParams(query)
    if (v === null || v === 'all') p.delete(k)
    else p.set(k, v)
    return p
  }
  const href = (id: string) => `/decisiones/${id}${query.size ? `?${query}` : ''}`

  const filters = Object.fromEntries(FILTERS.flatMap((f) => (query.get(f.key) ? [[f.param, query.get(f.key)!]] : [])))
  const deals = useDeals(filters)
  const gate = useGateQueue({ status: 'open' })

  const gateByOffer = new Map((gate.data?.items ?? []).map((g) => [g.offer_id, g]))
  const all = deals.data?.items ?? []
  // «Cola»: tratos con un elemento abierto en el gate, el más urgente primero. «Tratos»: el orden de ranking de la API.
  const rows =
    view === 'cola'
      ? all
          .filter((d) => gateByOffer.has(d.offer.id))
          .sort((a, b) => Date.parse(gateByOffer.get(a.offer.id)!.sla_due_at) - Date.parse(gateByOffer.get(b.offer.id)!.sla_due_at))
      : all
  const selected = dealId ? all.find((d) => d.id === dealId) : rows[0]
  const platforms = [...new Set([...all.map((d) => d.offer.platform), ...(query.get('plataforma') ? [query.get('plataforma')!] : [])])]
  const options = (values: string[], label: (v: string) => string) => [
    { value: 'all', label: t('filter.all') },
    ...values.map((value) => ({ value, label: label(value) })),
  ]
  const nowMs = Date.now()

  return (
    <>
      <nav aria-label={t('title')} className="flex gap-5 border-b border-line px-gutter-panel">
        {[
          { href: '/decisiones', icon: Handshake, text: t('nav.deals'), current: true },
          { href: '/decisiones/gate', icon: ListTodo, text: t('nav.gate'), current: false },
        ].map((l) => (
          <AppLink
            key={l.href}
            href={l.href}
            aria-current={l.current ? 'page' : undefined}
            className={`inline-flex items-center gap-1.5 py-3 no-underline ${l.current ? 'text-ink shadow-[inset_0_-2px_0_var(--accent)]' : 'text-ink-soft'}`}
          >
            <Icon icon={l.icon} size={20} />
            {l.text}
          </AppLink>
        ))}
      </nav>
      <KpiStrip />
      <div className="flex flex-wrap items-start">
        <div className="min-w-0 flex-[1_1_360px] border-r border-line">
          {inTranscript && selected ? (
            <Transcript deal={selected} backHref={href(selected.id)} />
          ) : (
            <>
              <div className="px-gutter-panel pt-4 pb-3">
                <Tabs value={view} onValueChange={(v) => go(pathname.replace(/^\/[^/]+/, ''), withParam('vista', v === 'cola' ? null : v), 'push')}>
                  <TabsList aria-label={t('views.label')}>
                    <TabsTrigger value="cola">
                      <Icon icon={ListTodo} />
                      {t('views.cola', { n: view === 'cola' ? rows.length : all.filter((d) => gateByOffer.has(d.offer.id)).length })}
                    </TabsTrigger>
                    <TabsTrigger value="tratos">
                      <Icon icon={Handshake} />
                      {t('views.tratos', { n: all.length })}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
              <div className="flex flex-wrap gap-2 px-gutter-panel pb-4">
                {FILTERS.map((f) => (
                  <Select
                    key={f.key}
                    label={t(`filter.${f.label}`)}
                    value={query.get(f.key) ?? 'all'}
                    options={options(f.key === 'plataforma' ? platforms : f.values, (v) => (f.ns ? t(`${f.ns}.${v}`) : v))}
                    onValueChange={(v) => go(pathname.replace(/^\/[^/]+/, ''), withParam(f.key, v), 'replace')}
                  />
                ))}
              </div>
              <ul className="m-0 list-none border-t border-line p-0">
                {deals.isPending && <li className="px-gutter-panel py-6 text-ink-soft">{t('loading')}</li>}
                {deals.isError && (
                  <li role="alert" className="px-gutter-panel py-6 text-bad">
                    {t('loadError')}{' '}
                    <Button onClick={() => void deals.refetch()}>{t('retry')}</Button>
                  </li>
                )}
                {deals.isSuccess && rows.length === 0 && (
                  <li className="px-gutter-panel py-6 text-ink-soft">
                    {t('empty')}{' '}
                    <AppLink href="/misiones" className="text-accent underline">{t('emptyNext')}</AppLink>
                  </li>
                )}
                {rows.map((d, n) => {
                  const on = d.id === selected?.id
                  const g = gateByOffer.get(d.offer.id)
                  const sla = g && remaining(g.sla_due_at, nowMs)
                  return (
                    <li
                      key={d.id}
                      className={`relative border-b border-line px-gutter-panel py-3 transition-[background-color] duration-(--fast) ease-apex [@media(hover:hover)]:hover:bg-panel ${on ? 'bg-panel shadow-[inset_2px_0_0_var(--accent)]' : ''}`}
                    >
                      <div className="flex justify-between gap-2 text-[13px] text-ink-muted">
                        <span>{view === 'cola' && g ? tg(`reasons.${g.causes[0]!}`) : t('rank', { n: d.recommendation_rank ?? n + 1 })}</span>
                        <span>{sla ? t(sla.overdue ? 'slaOverdue' : 'sla', { time: sla.label }) : d.offer.seller_name}</span>
                      </div>
                      <AppLink
                        href={href(d.id)}
                        aria-current={on ? 'true' : undefined}
                        className="my-0.5 mb-2 block font-medium text-ink no-underline after:absolute after:inset-0 after:content-['']"
                      >
                        {d.offer.title}
                      </AppLink>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <strong className="mr-1 font-semibold">
                          <MoneyDisplay amountMinor={d.offer.unit_price.amount_minor} currency={d.offer.unit_price.currency} locale={locale} />
                          {t('perUnit')}
                        </strong>
                        <DealBadges deal={d} />
                      </div>
                    </li>
                  )
                })}
              </ul>
            </>
          )}
        </div>
        <div className="min-w-0 flex-[999_1_560px]">
          {selected && <DealDetail key={selected.id} deal={selected} role={role} />}
          {dealId && deals.isSuccess && !selected && <p className="px-6 py-6 text-ink-soft">{t('notFound')}</p>}
        </div>
      </div>
    </>
  )
}

function Transcript({ deal, backHref }: { deal: Deal; backHref: string }) {
  const t = useTranslations('decisions')
  const negotiationId = deal.negotiation?.id
  const messages = useNegotiationMessages(negotiationId ?? '')
  const client = useQueryClient()
  // Live: a negotiation_message event of the mission of this deal makes the transcript read again.
  useEffect(() => {
    if (!negotiationId) return
    const handle = subscribeMissionEvents(deal.mission_id, {
      onEvent: (e) => {
        if (e.type === 'negotiation_message') void client.invalidateQueries({ queryKey: queryKeys.negotiationMessages(negotiationId) })
      },
    })
    return handle.close
  }, [deal.mission_id, negotiationId, client])
  return (
    <div className="px-gutter-panel py-4">
      <Button asChild>
        <AppLink href={backHref}>
          <Icon icon={ChevronLeft} />
          {t('transcript.back')}
        </AppLink>
      </Button>
      <h2 className="my-4 flex items-center gap-2 text-[17px] font-semibold">
        <Icon icon={ScrollText} />
        {t('transcript.title', { seller: deal.offer.seller_name })}
      </h2>
      {messages.isPending && <p className="text-ink-soft">{t('loading')}</p>}
      {messages.isError && <p role="alert" className="text-bad">{t('loadError')}</p>}
      {messages.data?.items.length === 0 && <p className="text-ink-soft">{t('transcript.empty')}</p>}
      {messages.data?.items.map((m) => (
        <div key={m.id} className="mb-2 border border-line bg-panel p-3">
          <div className="text-[13px] text-ink-muted">{t(`transcript.${m.role}`)}</div>
          {m.content}
        </div>
      ))}
    </div>
  )
}
