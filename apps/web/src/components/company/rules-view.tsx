'use client'

import { Badge, Button, Icon, Select } from '@apex/ui'
import { FilePen, History, Pencil, PenLine } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

import { rulesConfig, type Rule } from '@/fixtures/company'

const th = 'border-b border-line px-3 py-2 text-left text-[13px] font-normal text-ink-muted'
const td = 'border-b border-line px-3 py-2 align-top'
const groups = ['sanity', 'seller', 'signing', 'negotiation'] as const

export function RulesView() {
  const t = useTranslations('company.rules')
  const [selected, setSelected] = useState<Rule | null>(null)
  const { proposal } = rulesConfig
  const key = selected?.key ?? proposal.key

  return (
    <div className="flex flex-wrap items-start">
      <div className="flex min-w-0 flex-[999_1_720px] flex-col gap-6 px-10 py-6">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title', { version: rulesConfig.version })}</h1>
          <p className="m-0 mt-1.5 text-ink-soft">{t('intro')}</p>
        </div>
        {/* //todo_#167: el ámbito filtrará las reglas por categoría cuando haya backend */}
        <div className="flex items-end gap-3">
          <Select
            label={t('scope')}
            disabled
            defaultValue="all"
            options={rulesConfig.scopes.map((s) => ({ value: s, label: t(`scopes.${s}`) }))}
            className="w-44"
          />
          <span className="pb-2 text-[13px] text-ink-muted">{t('pending')}</span>
        </div>
        <table className="w-full border-collapse">
          <caption className="sr-only">{t('caption')}</caption>
          <thead>
            <tr>
              <th className={th}>{t('rule')}</th>
              <th className={`${th} text-right`}>{t('value')}</th>
              <th className={th}>{t('origin')}</th>
              <th className={`${th} text-right`}><span className="sr-only">{t('action')}</span></th>
            </tr>
          </thead>
          {groups.map((g) => (
            <tbody key={g}>
              <tr><th scope="rowgroup" colSpan={4} className="bg-panel px-3 py-2 text-left font-semibold">{t(`groups.${g}`)}</th></tr>
              {rulesConfig.rules.filter((r) => r.group === g).map((r) => (
                <tr key={r.key} className={r.origin === 'proposed' ? 'bg-accent-subtle' : undefined}>
                  <th scope="row" className={`${td} text-left font-normal`}>
                    {t(`names.${r.key.replace('.', '_')}`)}
                    <div className="font-mono text-[13px] text-ink-muted">{r.key}</div>
                  </th>
                  <td className={`${td} text-right tabular-nums`}>
                    {r.valueKey ? t(`values.${r.valueKey}`) : (r.value ?? <Badge tone="warn">{t('undefined')}</Badge>)}
                  </td>
                  <td className={`${td} text-[13px] text-ink-muted`}>{t(`origins.${r.origin}`)}</td>
                  <td className={`${td} text-right`}>
                    <Button variant="ghost" size="sm" aria-label={t('changeRule', { rule: t(`names.${r.key.replace('.', '_')}`) })} onClick={() => setSelected(r)}>
                      <Icon icon={Pencil} />{t('change')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <aside className="flex min-w-0 flex-[1_1_360px] flex-col gap-6 p-6">
        <div className="flex flex-col gap-3 border border-line bg-panel p-5">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={FilePen} />{t('proposalTitle')}</h2>
          <div className="flex justify-between gap-4"><span className="text-ink-muted">{t(`names.${key.replace('.', '_')}`)}</span><span className={selected ? 'text-ink-muted' : undefined}>{selected ? t('noNewValue') : proposal.change}</span></div>
          {/* //todo_#167: el impacto lo calcula el servidor con las ofertas abiertas */}
          {selected ? null : <p className="m-0 text-ink-muted">{t('impact', { n: proposal.impactCount })}</p>}
          <label className="flex flex-col gap-1">
            {t('reason')}
            <textarea rows={2} className="box-border border border-control-border bg-bg p-2.5 text-ink focus:border-accent" defaultValue={selected ? '' : proposal.reason} key={key} />
          </label>
          {/* //todo_#151: ceremonia de passkey y decisión firmada; //todo_#167: POST de cambio de configuración */}
          <Button variant="pri" disabledReason={t('pending')}><Icon icon={PenLine} />{t('sign')}</Button>
          <p className="m-0 text-[13px] text-ink-muted">{t('signNote')}</p>
        </div>
        <section>
          <h2 className="m-0 mb-2 flex items-center gap-2 text-base font-semibold"><Icon icon={History} />{t('history')}</h2>
          <ul className="m-0 list-none p-0">
            {rulesConfig.history.map((h) => (
              <li key={h.version} className="border-b border-line py-2">
                <strong className="font-semibold">{h.version}</strong>{' '}
                <span className="text-ink-muted">· {h.date} · {t(`by.${h.by}`)}</span>
                <div>{h.text}</div>
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  )
}
