'use client'

import { Badge, Button, Field, Icon, Input } from '@apex/ui'
import { CircleCheck, CircleX, PlugZap, Save, Sparkles, Trash2 } from 'lucide-react'
import { useFormatter, useTranslations } from 'next-intl'
import { useState, type FormEvent } from 'react'

import { ApiError } from '@/lib/api'
import {
  buildProviderPayload,
  isValidBaseUrl,
  MODEL_PRESETS,
  useClearLlmProvider,
  useLlmProvider,
  useSaveLlmProvider,
  useTestLlmProvider,
  type LlmProviderSettings,
} from '@/lib/api/provider'

export function ProviderView({ canEdit }: { canEdit: boolean }) {
  const t = useTranslations('company.provider')
  const settings = useLlmProvider()

  return (
    <div className="flex flex-wrap items-start">
      <div className="flex min-w-0 flex-[999_1_720px] flex-col gap-6 px-(--gutter-page) py-6">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
          <p className="m-0 mt-1.5 text-ink-soft">{t('intro')}</p>
        </div>
        {settings.isPending ? (
          <p role="status" className="m-0 text-ink-muted">
            {t('loading')}
          </p>
        ) : settings.isError ? (
          <div role="alert" className="flex items-center gap-3 border border-line bg-panel p-4">
            <span>
              {settings.error instanceof ApiError && settings.error.status === 403 ? t('noPermission') : t('loadFailed')}
            </span>
            <Button size="sm" onClick={() => void settings.refetch()}>
              {t('retry')}
            </Button>
          </div>
        ) : (
          <ProviderForm initial={settings.data} canEdit={canEdit} />
        )}
      </div>
      <aside className="flex min-w-0 flex-[1_1_360px] flex-col gap-6 p-6">
        <StatusPanel settings={settings.data} />
      </aside>
    </div>
  )
}

/**
 * The form state is seeded once from the server settings. Saving and clearing update it in place,
 * so a refetch never overwrites what the user is typing; the API stays the source of truth.
 */
function ProviderForm({ initial, canEdit }: { initial: LlmProviderSettings; canEdit: boolean }) {
  const t = useTranslations('company.provider')
  const save = useSaveLlmProvider()
  const test = useTestLlmProvider()
  const clear = useClearLlmProvider()
  const [baseUrl, setBaseUrl] = useState(initial.base_url ?? '')
  const [model, setModel] = useState(initial.model ?? '')
  const [apiKey, setApiKey] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)

  /** Editing invalidates the last save/clear feedback, not the last saved configuration. */
  const edited = () => {
    save.reset()
    clear.reset()
  }

  const baseUrlError = submitted
    ? !baseUrl.trim()
      ? t('baseUrlRequired')
      : !isValidBaseUrl(baseUrl)
        ? t('invalidUrl')
        : undefined
    : undefined
  const modelError = submitted && !model.trim() ? t('modelRequired') : undefined
  // The test endpoint reads the stored settings, not the form: it only makes sense once saved.
  const testBlocked = !canEdit
    ? t('noPermission')
    : !initial.base_url || !initial.model
      ? t('testNeedsConfig')
      : undefined

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitted(true)
    if (!canEdit || !isValidBaseUrl(baseUrl) || !model.trim()) return
    save.mutate(buildProviderPayload(baseUrl, model, apiKey), {
      onSuccess: () => {
        setSubmitted(false)
        setApiKey('')
        test.reset()
        clear.reset()
      },
    })
  }

  const clearAll = () =>
    clear.mutate(undefined, {
      onSuccess: () => {
        setBaseUrl('')
        setModel('')
        setApiKey('')
        setConfirmClear(false)
        setSubmitted(false)
        save.reset()
        test.reset()
      },
    })

  return (
    <>
      {!canEdit ? (
        <div role="status" className="border border-line bg-panel p-4 text-ink-soft">
          {t('noPermission')}
        </div>
      ) : null}

      <form noValidate className="flex flex-col gap-5 border border-line bg-panel p-5" onSubmit={submit}>
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
          <Icon icon={Sparkles} />
          {t('formTitle')}
        </h2>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
          <Field label={t('baseUrl')} hint={t('baseUrlHint')} error={baseUrlError} className="sm:col-span-2">
            {(control) => (
              <Input
                {...control}
                type="url"
                inputMode="url"
                autoComplete="off"
                spellCheck={false}
                className="font-mono"
                placeholder={t('baseUrlPlaceholder')}
                value={baseUrl}
                disabled={!canEdit}
                onChange={(e) => {
                  setBaseUrl(e.target.value)
                  edited()
                }}
              />
            )}
          </Field>
          <Field label={t('model')} hint={t('modelHint')} error={modelError}>
            {(control) => (
              <>
                <Input
                  {...control}
                  list="provider-model-presets"
                  autoComplete="off"
                  spellCheck={false}
                  className="font-mono"
                  placeholder={t('modelPlaceholder')}
                  value={model}
                  disabled={!canEdit}
                  onChange={(e) => {
                    setModel(e.target.value)
                    edited()
                  }}
                />
                <datalist id="provider-model-presets">
                  {MODEL_PRESETS.map((preset) => (
                    <option key={preset} value={preset} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
          <Field label={t('apiKey')} hint={t('apiKeyHint')}>
            {(control) => (
              <Input
                {...control}
                type="password"
                autoComplete="new-password"
                placeholder={t('apiKeyPlaceholder')}
                value={apiKey}
                disabled={!canEdit}
                onChange={(e) => {
                  setApiKey(e.target.value)
                  edited()
                }}
              />
            )}
          </Field>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="pri" busy={save.isPending} disabledReason={canEdit ? undefined : t('noPermission')}>
            <Icon icon={Save} />
            {t('save')}
          </Button>
          <Button
            type="button"
            variant="sec"
            busy={test.isPending}
            disabledReason={testBlocked}
            onClick={() => test.mutate()}
          >
            <Icon icon={PlugZap} />
            {t('test')}
          </Button>
          <span className="text-[13px] text-ink-muted">{t('testHint')}</span>
        </div>

        {save.isSuccess ? (
          <p role="status" className="m-0 text-good">
            {t('saved')}
          </p>
        ) : null}
        {save.isError ? (
          <p role="alert" className="m-0 text-bad">
            {save.error instanceof ApiError && save.error.status === 403 ? t('noPermission') : t('saveFailed')}
          </p>
        ) : null}

        {test.data ? (
          <div role="status" aria-live="polite" className="flex flex-col gap-2 border border-line bg-bg p-3">
            <Badge tone={test.data.ok ? 'ok' : 'bad'} icon={test.data.ok ? CircleCheck : CircleX}>
              {test.data.ok ? t('testOk') : t('testFailed')}
            </Badge>
            {test.data.ok ? (
              test.data.models.length > 0 ? (
                <div className="flex flex-col gap-1">
                  <span className="text-[13px] text-ink-muted">
                    {t('testModels', { count: test.data.models.length })}
                  </span>
                  <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                    {test.data.models.map((name) => (
                      <li key={name}>
                        <Badge tone="plano" className="font-mono">
                          {name}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="m-0 text-[13px] text-ink-muted">{t('testNoModels')}</p>
              )
            ) : (
              <p className="m-0 text-[13px] text-bad">{test.data.error ?? t('testFailed')}</p>
            )}
          </div>
        ) : null}
        {test.isError ? (
          <p role="alert" className="m-0 text-bad">
            {test.error instanceof ApiError && test.error.status === 403 ? t('noPermission') : t('testRequestFailed')}
          </p>
        ) : null}
      </form>

      <section className="flex flex-col gap-3 border border-line bg-panel p-5">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
          <Icon icon={Trash2} />
          {t('clearTitle')}
        </h2>
        <p className="m-0 text-ink-soft">{t('clearBody')}</p>
        {confirmClear ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="danger" busy={clear.isPending} onClick={clearAll}>
              <Icon icon={Trash2} />
              {t('clearConfirm')}
            </Button>
            <Button variant="ghost" onClick={() => setConfirmClear(false)}>
              {t('clearCancel')}
            </Button>
          </div>
        ) : (
          <div>
            <Button
              variant="danger"
              disabledReason={
                !canEdit
                  ? t('noPermission')
                  : !initial.base_url && !initial.model
                    ? t('clearNothing')
                    : undefined
              }
              onClick={() => setConfirmClear(true)}
            >
              <Icon icon={Trash2} />
              {t('clear')}
            </Button>
          </div>
        )}
        {clear.isSuccess ? (
          <p role="status" className="m-0 text-ink-soft">
            {t('cleared')}
          </p>
        ) : null}
        {clear.isError ? (
          <p role="alert" className="m-0 text-bad">
            {clear.error instanceof ApiError && clear.error.status === 403 ? t('noPermission') : t('clearFailed')}
          </p>
        ) : null}
      </section>
    </>
  )
}

function StatusPanel({ settings }: { settings: LlmProviderSettings | undefined }) {
  const t = useTranslations('company.provider')
  const format = useFormatter()
  const updated = settings?.updated_at ? new Date(settings.updated_at) : null
  const updatedLabel =
    updated && !Number.isNaN(updated.getTime())
      ? format.dateTime(updated, { dateStyle: 'medium', timeStyle: 'short' })
      : settings
        ? t('never')
        : '…'
  return (
    <section className="flex flex-col gap-4 border border-line bg-panel p-5">
      <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
        <Icon icon={Sparkles} />
        {t('statusTitle')}
      </h2>
      <div className="flex flex-col gap-1">
        <span className="text-[13px] text-ink-muted">{t('keyStatus')}</span>
        {settings?.api_key_set ? (
          <Badge tone="ok">{t('keySet')}</Badge>
        ) : settings ? (
          <Badge tone="neutro">{t('keyMissing')}</Badge>
        ) : (
          <span className="text-ink-muted">…</span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-[13px] text-ink-muted">{t('updatedAt')}</span>
        <span>{updatedLabel}</span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-[13px] text-ink-muted">{t('currentBaseUrl')}</span>
        <span className="font-mono break-all">{settings?.base_url ?? '—'}</span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-[13px] text-ink-muted">{t('currentModel')}</span>
        <span className="font-mono">{settings?.model ?? '—'}</span>
      </div>
      <p className="m-0 text-[13px] text-ink-muted">{t('formNote')}</p>
    </section>
  )
}
