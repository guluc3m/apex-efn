'use client'

import { Badge, Button, Icon, Input, Label } from '@apex/ui'
import { FilePen, History, Pencil, Send } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'

import { SignDecisionButton } from '@/components/signing/sign-decision-button'
import { ApiError, useConfigVersions, useEffectiveConfig, useProposeConfigChange } from '@/lib/api'
import { parsePatchValue, toRuleRows, type RuleRow } from '@/lib/config-rules'

const th = 'border-b border-line px-3 py-2 text-left text-[13px] font-normal text-ink-muted'
const td = 'border-b border-line px-3 py-2 align-top'
const groups = ['sanity', 'seller', 'signing', 'negotiation', 'other'] as const
const GROUP_OF: Record<string, (typeof groups)[number]> = { sanity: 'sanity', seller: 'seller', signing: 'signing', approval: 'signing', neg: 'negotiation' }

export function RulesView({ canChange }: { canChange: boolean }) {
  const t = useTranslations('company.rules')
  const locale = useLocale()
  const [category, setCategory] = useState('')
  const [applied, setApplied] = useState<string | undefined>(undefined)
  const [selected, setSelected] = useState<RuleRow | null>(null)
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const history = useConfigVersions()
  const config = useEffectiveConfig(applied)
  const propose = useProposeConfigChange()
  const rows = config.data ? toRuleRows(config.data, locale) : []
  const name = (key: string) => (t.has(`names.${key.replace('.', '_')}`) ? t(`names.${key.replace('.', '_')}`) : key)
  const proposalBlocked = !canChange ? t('noPermission') : !selected || value.trim() === '' ? t('pick') : reason.trim() === '' ? t('reasonRequired') : undefined

  const submit = () => {
    if (!config.data || !selected) return
    propose.mutate({
      base_config_version: config.data.config_version,
      category: applied ?? null,
      patch: nest(selected.key, parsePatchValue(value)),
      reason: reason.trim(),
    })
  }

  return (
    <div className="flex flex-wrap items-start">
      <div className="flex min-w-0 flex-[999_1_720px] flex-col gap-6 px-10 py-6">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title', { version: config.data?.config_version ?? '…' })}</h1>
          <p className="m-0 mt-1.5 text-ink-soft">{t('intro')}</p>
          {config.data ? <p className="m-0 mt-1 font-mono text-[13px] text-ink-muted">{t('version', { version: config.data.config_version, hash: config.data.content_hash.slice(0, 15) })}</p> : null}
        </div>
        <form
          className="flex items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            setApplied(category.trim() || undefined)
            setSelected(null)
          }}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="rules-category">{t('category')}</Label>
            <Input id="rules-category" value={category} onChange={(e) => setCategory(e.target.value)} placeholder={t('categoryHint')} className="w-56" />
          </div>
          <Button type="submit">{t('apply')}</Button>
        </form>

        {config.isPending ? (
          <p role="status" className="m-0 text-ink-muted">{t('loading')}</p>
        ) : config.isError ? (
          <div role="alert" className="flex items-center gap-3 border border-line bg-panel p-4">
            <span>{config.error instanceof ApiError && config.error.status === 403 ? t('noPermission') : t('error')}</span>
            <Button size="sm" onClick={() => void config.refetch()}>{t('retry')}</Button>
          </div>
        ) : rows.length === 0 ? (
          <p className="m-0 text-ink-muted">{t('empty')}</p>
        ) : (
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
            {groups.map((g) => {
              const inGroup = rows.filter((r) => (GROUP_OF[r.group] ?? 'other') === g)
              if (inGroup.length === 0) return null
              return (
                <tbody key={g}>
                  <tr><th scope="rowgroup" colSpan={4} className="bg-panel px-3 py-2 text-left font-semibold">{g === 'other' ? t('other') : t(`groups.${g}`)}</th></tr>
                  {inGroup.map((r) => (
                    <tr key={r.key}>
                      <th scope="row" className={`${td} text-left font-normal`}>
                        {name(r.key)}
                        <div className="font-mono text-[13px] text-ink-muted">{r.key}</div>
                      </th>
                      <td className={`${td} text-right tabular-nums`}>{r.display ?? <Badge tone="warn">{t('undefined')}</Badge>}</td>
                      <td className={`${td} text-[13px] text-ink-muted`}>{t(`origins.${r.layer}`)}</td>
                      <td className={`${td} text-right`}>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabledReason={canChange ? undefined : t('noPermission')}
                          aria-label={t('changeRule', { rule: name(r.key) })}
                          onClick={() => {
                            setSelected(r)
                            setValue('')
                            propose.reset()
                          }}
                        >
                          <Icon icon={Pencil} />{t('change')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              )
            })}
          </table>
        )}
      </div>
      <aside className="flex min-w-0 flex-[1_1_360px] flex-col gap-6 p-6">
        <div className="flex flex-col gap-3 border border-line bg-panel p-5">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={FilePen} />{t('proposalTitle')}</h2>
          {selected ? (
            <>
              <div className="flex justify-between gap-4"><span className="text-ink-muted">{name(selected.key)}</span><span>{selected.display ?? t('undefined')}</span></div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="rules-new-value">{t('newValue')}</Label>
                <Input id="rules-new-value" value={value} onChange={(e) => setValue(e.target.value)} placeholder={t('newValueHint')} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="rules-reason">{t('reason')}</Label>
                <Input id="rules-reason" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
              </div>
            </>
          ) : (
            <p className="m-0 text-ink-muted">{canChange ? t('pick') : t('noPermission')}</p>
          )}
          <Button variant="sec" disabledReason={proposalBlocked ?? (propose.isPending ? t('loading') : undefined)} onClick={submit}>
            <Icon icon={Send} />{t('propose')}
          </Button>
          {propose.isSuccess ? <p role="status" className="m-0">{t('proposed', { id: propose.data.decision_id })}</p> : null}
          {propose.isError ? <p role="alert" className="m-0 text-danger">{propose.error instanceof ApiError && propose.error.status === 409 ? t('stale') : t('proposeFailed')}</p> : null}
          <SignDecisionButton {...(propose.data ? { decisionId: propose.data.decision_id } : {})} reasonWithout={t('signDisabled')}>{t('sign')}</SignDecisionButton>
          <p className="m-0 text-[13px] text-ink-muted">{t('signNote')}</p>
        </div>
        <section>
          <h2 className="m-0 mb-2 flex items-center gap-2 text-base font-semibold"><Icon icon={History} />{t('history')}</h2>
          {history.isError ? (
            <p className="m-0 text-ink-muted">{t('historyPending')}</p>
          ) : history.data && history.data.items.length > 0 ? (
            <ol className="m-0 flex list-none flex-col gap-2 p-0">
              {history.data.items.map((v) => (
                <li key={v.config_version} className="border-b border-line pb-2">
                  <div className="flex justify-between gap-4">
                    <span className="font-mono">v{v.config_version}{v.category ? ` · ${v.category}` : ''}</span>
                    <time dateTime={v.created_at} className="text-[13px] text-ink-muted">{new Date(v.created_at).toLocaleString(locale)}</time>
                  </div>
                  {v.reason ? <p className="m-0 text-ink-soft">{v.reason}</p> : null}
                  {v.summary && v.summary.length > 0 ? <p className="m-0 font-mono text-[13px] text-ink-muted">{v.summary.join(', ')}</p> : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="m-0 text-ink-muted">{history.isPending ? t('loading') : t('historyEmpty')}</p>
          )}
        </section>
      </aside>
    </div>
  )
}

/** `a.b.c` + v -> `{a:{b:{c:v}}}`: the deep-merge patch shape the contract asks for. */
function nest(key: string, v: unknown): Record<string, unknown> {
  return key.split('.').reduceRight<unknown>((acc, part) => ({ [part]: acc }), v) as Record<string, unknown>
}
