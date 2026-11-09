'use client'

import { Button, ConfidenceBandBadge, FinancialVerdictBadge, Icon, PriceBandBadge, Select, SignatureStatusBadge } from '@apex/ui'
import { ArrowDown, ArrowLeft, ArrowUp, Download, PiggyBank, Scale } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

import { AppLink } from '@/components/app-link'
import type { CompareFixture, ProfileKey } from '@/fixtures/compare'

import { ScoreChart } from './score-chart'

const PROFILES: ProfileKey[] = ['operative', 'cfo']

export function CompareView({ data, missionId }: { data: CompareFixture; missionId: string }) {
  const t = useTranslations('compare')
  const [profile, setProfile] = useState<ProfileKey>('operative')
  const p = data.profiles[profile]
  const rows = p.ranking.map((r, i) => ({ ...r, rank: i + 1, f: data.finalists.find((f) => f.id === r.id)! }))
  const first = rows[0]!
  const th = 'border-b border-line px-3 py-2 text-left font-normal text-ink-muted'
  const td = 'border-b border-line px-3 py-2 align-top'

  return (
    <main id="contenido" className="flex flex-col">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-(--gutter-page) py-6">
        <div className="flex flex-col gap-1">
          <AppLink href={`/misiones/${missionId}`} className="inline-flex items-center gap-1 text-ink-soft">
            <Icon icon={ArrowLeft} label="" /> {t('back')}
          </AppLink>
          <div className="text-[13px] text-ink-muted">{t('context', { code: data.missionCode, n: rows.length })}</div>
          <h1 className="m-0 text-xl font-semibold">{p.headline}</h1>
          <p className="m-0 text-ink-soft">{p.explanation}</p>
        </div>
        <div className="flex items-end gap-2">
          <Select
            label={t('profile')}
            value={profile}
            onValueChange={(v) => setProfile(v as ProfileKey)}
            options={PROFILES.map((k) => ({ value: k, label: t(`profiles.${k}`) }))}
          />
          <Button variant="sec" disabledReason={t('pending')}>
            <Icon icon={Download} label="" /> {t('export')}
          </Button>
          <Button variant="pri" disabledReason={t('pending')}>
            <Icon icon={Scale} label="" /> {t('decide', { name: first.f.name })}
          </Button>
        </div>
      </header>

      <div className="flex flex-col gap-8 px-(--gutter-page) py-6">
        <table className="w-full table-fixed border-collapse">
          <caption className="sr-only">{t('tableCaption')}</caption>
          <thead>
            <tr>
              <th scope="col" className={th}>{t('rows.criterion')}</th>
              {rows.map((r) => (
                <th key={r.id} scope="col" className={th}>
                  <AppLink href={`/decisiones/${r.f.dealId}`} className="text-ink underline">{r.f.name}</AppLink> · {t('rank', { n: r.rank })}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row" className={th}>{t('rows.price')}</th>
              {rows.map((r) => (
                <td key={r.id} className={td}>
                  <strong className="font-semibold">{r.f.price}</strong>{' '}
                  <span className={r.f.delta.dir === 'down' ? 'inline-flex items-center text-good' : 'inline-flex items-center text-bad'}>
                    <Icon icon={r.f.delta.dir === 'down' ? ArrowDown : ArrowUp} label={t(`delta.${r.f.delta.dir}`)} />
                    {r.f.delta.label}
                  </span>
                  {r.f.note && <div className="text-[13px] text-ink-muted">{r.f.note}</div>}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.band')}</th>
              {rows.map((r) => <td key={r.id} className={td}><PriceBandBadge band={r.f.priceBand} label={t(`price.${r.f.priceBand}`)} /></td>)}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.confidence')}</th>
              {rows.map((r) => <td key={r.id} className={td}><ConfidenceBandBadge band={r.f.confidence.band} label={`${t(`confidence.${r.f.confidence.band}`)} · ${r.f.confidence.score}`} /></td>)}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.verdict')}</th>
              {rows.map((r) => <td key={r.id} className={td}><FinancialVerdictBadge verdict={r.f.verdict} label={t(`verdict.${r.f.verdict}`)} /></td>)}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.signature')}</th>
              {rows.map((r) => <td key={r.id} className={td}><SignatureStatusBadge status={r.f.signature} label={t(`signature.${r.f.signature}`)} /></td>)}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.landed')}</th>
              {rows.map((r) => <td key={r.id} className={td}>{r.f.landed}</td>)}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.lead')}</th>
              {rows.map((r) => <td key={r.id} className={td}>{r.f.lead}</td>)}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.score')}</th>
              {rows.map((r) => <td key={r.id} className={td}>{r.score}</td>)}
            </tr>
            <tr>
              <th scope="row" className={th}>{t('rows.vsFirst')}</th>
              {rows.map((r) => <td key={r.id} className={td}>{r.vsFirst || <span className="text-ink-muted">—</span>}</td>)}
            </tr>
          </tbody>
        </table>
        <p className="m-0 text-[13px] text-ink-muted">{t('deltaNote', { median: data.median })}</p>

        <div className="flex flex-wrap gap-8">
          <div className="min-w-0 flex-[2_1_560px]">
            <ScoreChart rows={rows.map((r) => ({ name: r.f.name, score: r.score, parts: r.parts }))} />
          </div>
          <section className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
            <h2 className="m-0 inline-flex items-center gap-2 text-base font-semibold"><Icon icon={PiggyBank} label="" /> {t('savings.title')}</h2>
            <dl className="m-0 flex flex-col gap-4">
              {([['list', data.savings.list], ['median', data.savings.median], ['year', data.savings.year]] as const).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[13px] text-ink-muted">{t(`savings.${k}`, { category: data.savings.category })}</dt>
                  <dd className="m-0 text-xl">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="border border-line bg-panel p-3">
              <div className="text-[13px] text-ink-muted">{t('savings.memory')}</div>
              {data.savings.memory}
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}
