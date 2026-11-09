'use client'

import { Button, Icon, MoneyDisplay, Select, Tabs, TabsList, TabsTrigger } from '@apex/ui'
import { ChevronLeft, Handshake, ListTodo, ScrollText } from 'lucide-react'
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'

import { AppLink } from '@/components/app-link'
import { deals, rankScore, views, type Deal, type Profile } from '@/fixtures/decisions'

import { DealBadges } from './deal-badges'
import { DealDetail } from './deal-detail'
import { KpiStrip } from './kpi-strip'

type FilterKey = 'precio' | 'confianza' | 'veredicto' | 'plataforma' | 'firma'
const FILTERS: { key: FilterKey; label: string; ns?: string; values: string[]; pick: (d: Deal) => string | undefined }[] = [
  { key: 'precio', label: 'price', ns: 'band', values: ['normal', 'atypical', 'implausible'], pick: (d) => d.band },
  { key: 'confianza', label: 'confidence', ns: 'conf', values: ['high', 'medium', 'low', 'untrusted'], pick: (d) => d.conf },
  { key: 'veredicto', label: 'verdict', ns: 'verdict', values: ['within_budget', 'stretch', 'out_of_budget'], pick: (d) => d.verdict },
  { key: 'plataforma', label: 'platform', values: ['Plataforma 1', 'Plataforma 2'], pick: (d) => d.platform },
  { key: 'firma', label: 'signature', ns: 'sig', values: ['pending', 'signed'], pick: (d) => d.sig?.status },
]
const byId = new Map(deals.map((d) => [d.id, d]))

/** Maestro-detalle. El trato y la pestaña van a la URL con push; los filtros con replace (#141). */
export function DecisionsView() {
  const t = useTranslations('decisions')
  const locale = useLocale()
  const router = useRouter()
  const pathname = usePathname()
  const query = useSearchParams()
  const { dealId } = useParams<{ dealId?: string }>()
  const inTranscript = pathname.endsWith('/transcripcion')

  const view = query.get('vista') === 'tratos' ? 'tratos' : 'cola'
  const profile: Profile = query.get('perfil') === 'cfo' ? 'cfo' : 'comprador'
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

  const ids = view === 'cola' ? views.cola : views.tratos[profile]
  const active = FILTERS.filter((f) => query.get(f.key))
  const rows = ids
    .map((id) => byId.get(id)!)
    .filter((d) => active.every((f) => f.pick(d) === query.get(f.key)))
  const selected = (dealId && byId.get(dealId)) || rows[0]
  const options = (values: string[], label: (v: string) => string) => [
    { value: 'all', label: t('filter.all') },
    ...values.map((value) => ({ value, label: label(value) })),
  ]

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
                      {t('views.cola', { n: views.cola.length })}
                    </TabsTrigger>
                    <TabsTrigger value="tratos">
                      <Icon icon={Handshake} />
                      {t('views.tratos', { n: views.tratos[profile].length })}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
              {view === 'tratos' && (
                <div className="px-gutter-panel pb-3">
                  <Select
                    label={t('filter.profile')}
                    value={profile}
                    options={(['comprador', 'cfo'] as const).map((value) => ({ value, label: t(`profile.${value}`) }))}
                    onValueChange={(v) => go(pathname.replace(/^\/[^/]+/, ''), withParam('perfil', v === 'comprador' ? null : v), 'replace')}
                  />
                  <p className="mt-2 text-[13px] text-ink-muted">{t(`whyRank.${profile}`)}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2 px-gutter-panel pb-4">
                {FILTERS.map((f) => (
                  <Select
                    key={f.key}
                    label={t(`filter.${f.label}`)}
                    value={query.get(f.key) ?? 'all'}
                    options={options(f.values, (v) => (f.ns ? t(`${f.ns}.${v}`) : v))}
                    onValueChange={(v) => go(pathname.replace(/^\/[^/]+/, ''), withParam(f.key, v), 'replace')}
                  />
                ))}
              </div>
              <ul className="m-0 list-none border-t border-line p-0">
                {rows.length === 0 && (
                  <li className="px-gutter-panel py-6 text-ink-soft">
                    {t('empty')}{' '}
                    <AppLink href="/misiones" className="text-accent underline">{t('emptyNext')}</AppLink>
                  </li>
                )}
                {rows.map((d, n) => {
                  const on = d.id === selected?.id
                  return (
                    <li
                      key={d.id}
                      className={`relative border-b border-line px-gutter-panel py-3 transition-[background-color] duration-(--fast) ease-apex [@media(hover:hover)]:hover:bg-panel ${on ? 'bg-panel shadow-[inset_2px_0_0_var(--accent)]' : ''}`}
                    >
                      <div className="flex justify-between gap-2 text-[13px] text-ink-muted">
                        <span>{view === 'cola' ? t(`cause.${d.cause}`) : t('rank', { n: n + 1, score: rankScore[profile][d.id]?.toFixed(2) ?? '' })}</span>
                        <span>{view === 'cola' ? t('sla', { time: d.sla ?? '' }) : d.seller}</span>
                      </div>
                      <AppLink
                        href={href(d.id)}
                        aria-current={on ? 'true' : undefined}
                        className="my-0.5 mb-2 block font-medium text-ink no-underline after:absolute after:inset-0 after:content-['']"
                      >
                        {d.title}
                      </AppLink>
                      {!d.tenant && (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <strong className="mr-1 font-semibold">
                            <MoneyDisplay amountMinor={d.unitMinor ?? 0} currency="EUR" locale={locale} />
                            {t('perUnit')}
                          </strong>
                          <DealBadges deal={d} />
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            </>
          )}
        </div>
        <div className="min-w-0 flex-[999_1_560px]">{selected && <DealDetail key={selected.id} deal={selected} profile={profile} />}</div>
      </div>
    </>
  )
}

function Transcript({ deal, backHref }: { deal: Deal; backHref: string }) {
  const t = useTranslations('decisions')
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
        {t('transcript.title', { seller: deal.seller ?? '' })}
      </h2>
      {deal.transcript?.map((m, i) => (
        <div key={i} className="mb-2 border border-line bg-panel p-3">
          <div className="text-[13px] text-ink-muted">{t(`transcript.${m.who}`)}</div>
          {m.text}
        </div>
      ))}
      {/* //todo_#148: transcripción real y en vivo (SSE de la negociación) */}
    </div>
  )
}
