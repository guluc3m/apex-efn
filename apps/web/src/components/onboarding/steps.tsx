'use client'

import { Button, Checkbox, Icon } from '@apex/ui'
import { FileText, FolderOpen, Download, Plus, Upload } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { FormProvider, useForm, useFormContext, type FieldValues } from 'react-hook-form'
import type { z } from 'zod'

import { AppLink } from '@/components/app-link'
import { certifications, effectiveThresholds } from '@/fixtures/onboarding'
import { api } from '@/lib/api'
import { ensureSession } from '@/lib/onboarding-session'
import { useOnboarding } from '@/stores/onboarding'

import { CellInput, CheckGroup, SelectField, TextField } from './fields'
import { schemas, zodResolver, type Drafts, type FormStepId } from './schemas'

export const FORM_ID = 'paso-form'

/** Formulario de un paso: RHF + zod, borrador en Zustand en cada cambio, `onValid` al enviar. */
export function StepForm<K extends FormStepId>({ id, onValid, children }: { id: K; onValid: () => void | Promise<void>; children: ReactNode }) {
  const save = useOnboarding((s) => s.save)
  const form = useForm<FieldValues>({
    resolver: zodResolver(schemas[id] as z.ZodType<FieldValues, z.ZodTypeDef, FieldValues>),
    defaultValues: useOnboarding.getState().drafts[id],
    mode: 'onTouched',
  })
  useEffect(() => {
    const sub = form.watch((values) => save(id, values as Drafts[K]))
    return () => sub.unsubscribe()
  }, [form, id, save])
  return (
    <FormProvider {...form}>
      <form
        id={FORM_ID}
        noValidate
        className="flex flex-col gap-6"
        onSubmit={(e) => {
          void form.handleSubmit((values) => {
            save(id, values as Drafts[K])
            void onValid()
          })(e)
        }}
      >
        {children}
      </form>
    </FormProvider>
  )
}

const grid = 'grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4'
const th = 'border-b border-line px-3 py-2 text-left text-[13px] font-normal text-ink-muted'
const td = 'border-b border-line px-3 py-2'

function useOptions(group: string, values: string[]) {
  const t = useTranslations(`onboarding.options.${group}`)
  return values.map((value) => ({ value, label: t(value) }))
}

export function CompanyStep() {
  const t = useTranslations('onboarding.fields')
  const country = useOptions('country', ['es'])
  const customs = useOptions('customs', ['eori'])
  const { register } = useFormContext()
  return (
    <div className={grid}>
      <TextField name="razonSocial" label={t('legalName')} />
      <TextField name="cif" label={t('taxId')} />
      <SelectField name="pais" label={t('country')} options={country} />
      <SelectField name="aduana" label={t('customs')} options={customs} />
      <TextField name="direccion" label={t('shipping')} className="col-span-full" />
      <div className="col-span-full">
        <Checkbox label={t('billingSame')} {...register('facturacionIgual')} />
      </div>
    </div>
  )
}

export function SectorStep() {
  const t = useTranslations('onboarding.fields')
  const frequency = useOptions('frequency', ['monthly', 'quarterly', 'occasional'])
  return (
    <div className={grid}>
      <TextField name="cnae" label={t('cnae')} />
      <SelectField name="frecuencia" label={t('frequency')} options={frequency} />
      <TextField name="compras" label={t('purchases')} long className="col-span-full" />
      <TextField name="estacionalidad" label={t('seasonality')} className="col-span-full" />
    </div>
  )
}

export function BudgetStep() {
  const t = useTranslations('onboarding')
  const currency = useOptions('currency', ['EUR', 'USD', 'CNY'])
  const payment = useOptions('payment', ['d30', 'd60', 'd90', 'prepaid'])
  const rows = useOnboarding((s) => s.drafts.presupuesto.categorias)
  return (
    <>
      <div className={grid}>
        <SelectField name="divisa" label={t('fields.currency')} options={currency} />
        <SelectField name="pago" label={t('fields.payment')} options={payment} />
        <TextField name="colchon" label={t('fields.buffer')} />
      </div>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className={th}>{t('fields.category')}</th>
            <th className={`${th} text-right`}>{t('fields.envelope')}</th>
            <th className={`${th} text-right`}>{t('fields.maxPerOrder')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id}>
              <th scope="row" className={`${td} text-left font-normal`}>{r.label}</th>
              <td className={`${td} text-right`}>
                <CellInput name={`categorias.${i}.envelope`} label={`${r.label}: ${t('fields.envelope')}`} />
              </td>
              <td className={`${td} text-right`}>
                <CellInput name={`categorias.${i}.maximo`} label={`${r.label}: ${t('fields.maxPerOrder')}`} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* //todo_#152: alta de categorías nuevas (necesita el catálogo del servidor) */}
      <div>
        <Button variant="sec" disabledReason={t('pending')}>
          <Icon icon={Plus} />
          {t('fields.addCategory')}
        </Button>
      </div>
    </>
  )
}

export function PolicyStep() {
  const t = useTranslations('onboarding.fields')
  const trust = useOptions('trust', ['medium', 'high'])
  const lateness = useOptions('lateness', ['none', 'late5', 'late10'])
  return (
    <>
      <div className={grid}>
        <TextField name="aprobacion" label={t('approvalFrom')} hint={t('amountRequired')} />
        <TextField name="doble" label={t('dualFrom')} hint={t('amountRequired')} />
        <SelectField name="confianza" label={t('minTrust')} options={trust} />
        <SelectField name="plazo" label={t('lateness')} options={lateness} />
      </div>
      <CheckGroup name="certificaciones" legend={t('certifications')} options={certifications.map((c) => ({ value: c, label: c }))} />
      <TextField name="paisesExcluidos" label={t('excludedCountries')} hint={t('none')} />
      <TextField name="vetados" label={t('bannedSellers')} hint={t('none')} />
      <section aria-labelledby="eff-title" className="flex flex-col gap-2 border border-line bg-panel p-4">
        <h2 id="eff-title" className="m-0 text-[13px] font-normal text-ink-muted">{t('effective')}</h2>
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
          {effectiveThresholds.map((e) => (
            <div key={e.key} className="contents">
              <dt className="text-ink-soft">{t(`thresholds.${e.key}`)}</dt>
              <dd className="m-0 text-right tabular-nums">{e.value ?? t('unset')}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  )
}

export function NegotiationStep() {
  const t = useTranslations('onboarding')
  const aggressiveness = useOptions('aggressiveness', ['balanced', 'conservative', 'aggressive'])
  const tone = useOptions('tone', ['formal', 'close'])
  const language = useOptions('language', ['seller', 'es', 'en'])
  const counterparts = useOptions('counterparts', ['volume', 'prepay', 'framework', 'longerTerm'])
  const rows = useOnboarding((s) => s.drafts.negociacion.categorias)
  return (
    <>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className={th}>{t('fields.category')}</th>
            <th className={`${th} text-right`}>{t('fields.targetDiscount')}</th>
            <th className={`${th} text-right`}>{t('fields.maxDiscount')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id}>
              <th scope="row" className={`${td} text-left font-normal`}>{r.label}</th>
              <td className={`${td} text-right`}>
                <CellInput name={`categorias.${i}.objetivo`} label={`${r.label}: ${t('fields.targetDiscount')}`} describedBy="discount-note" />
              </td>
              <td className={`${td} text-right`}>
                <CellInput name={`categorias.${i}.maximo`} label={`${r.label}: ${t('fields.maxDiscount')}`} describedBy="discount-note" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p id="discount-note" className="m-0 text-[13px] text-ink-muted">{t('fields.discountNote')}</p>
      <div className={grid}>
        <SelectField name="agresividad" label={t('fields.aggressiveness')} options={aggressiveness} />
        <SelectField name="tono" label={t('fields.tone')} options={tone} />
        <SelectField name="idioma" label={t('fields.language')} options={language} />
      </div>
      <CheckGroup name="contrapartidas" legend={t('fields.counterparts')} options={counterparts} />
      <div className="border border-line bg-panel p-4 text-[13px] text-ink-muted">{t('fields.sendMode')}</div>
    </>
  )
}

const formatSize = (bytes: number) => (bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`)

/** Solo se guardan nombre y tamaño; el archivo no se lee. */
export function FinanceStep() {
  const t = useTranslations('onboarding.finance')
  const csv = useOnboarding((s) => s.csv)
  const setCsv = useOnboarding((s) => s.setCsv)
  const input = useRef<HTMLInputElement>(null)
  // The File never enters the store: only its name/size and the server's report do.
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const result = useOnboarding((s) => s.financialImport)
  const setResult = useOnboarding((s) => s.setFinancialImport)
  const upload = async () => {
    if (!file) return
    setBusy(true)
    setFailed(false)
    try {
      setResult(await api.uploadFinancialCsv(await ensureSession(), file))
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <div className="flex flex-col items-start gap-1 border border-dashed border-line-strong p-6">
        <strong className="inline-flex items-center gap-2 font-semibold">
          <Icon icon={Upload} />
          {t('drop')}
        </strong>
        <p className="m-0 mb-3 text-[13px] text-ink-muted">{t('format')}</p>
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          tabIndex={-1}
          aria-label={t('choose')}
          onChange={(e) => {
            const picked = e.target.files?.[0]
            setFile(picked ?? null)
            setResult(null)
            setCsv(picked ? { name: picked.name, size: picked.size } : null)
          }}
        />
        <Button variant="sec" onClick={() => input.current?.click()}>
          <Icon icon={FolderOpen} />
          {t('choose')}
        </Button>
      </div>
      {csv && (
        <div className="flex flex-col gap-2 border border-line bg-panel p-4" role="status">
          <strong className="inline-flex items-center gap-2 font-semibold">
            <Icon icon={FileText} />
            {csv.name}
          </strong>
          <span className="text-[13px] text-ink-muted">{t('selected', { size: formatSize(csv.size) })}</span>
          <div>
            <Button variant="pri" onClick={() => void upload()} disabled={busy || !file}>
              <Icon icon={Upload} />
              {busy ? t('uploading') : t('upload')}
            </Button>
          </div>
        </div>
      )}
      {failed && (
        <p role="alert" className="m-0 text-bad">
          {t('uploadError')}
        </p>
      )}
      {result && (
        <section className="flex flex-col gap-2 border border-line bg-panel p-4" role="status" aria-label={t('resultTitle')}>
          <strong className="font-semibold">{t('result', { ok: result.report.rows_ok, rejected: result.report.rows_rejected })}</strong>
          <ul className="m-0 list-none p-0 text-[13px] text-ink-muted">
            {result.report.rejections.map((r) => (
              <li key={`${r.row}-${r.reason_code}`}>{t('rejection', { row: r.row, message: r.message })}</li>
            ))}
          </ul>
          {result.report.warnings.map((w) => (
            <p key={w} className="m-0 text-[13px]">
              {w}
            </p>
          ))}
          <span className="text-[13px] text-ink-muted">{t('notActivated')}</span>
          <div>
            <Button variant="sec" size="sm" asChild>
              <AppLink href={`/onboarding/finanzas/${result.id}`}>{t('viewReport')}</AppLink>
            </Button>
          </div>
        </section>
      )}
      {/* //todo_#152: plantilla y documentación de métricas aceptadas */}
      <div>
        <Button variant="ghost" size="sm" disabledReason={t('pending')}>
          <Icon icon={Download} />
          {t('template')}
        </Button>
      </div>
    </>
  )
}
