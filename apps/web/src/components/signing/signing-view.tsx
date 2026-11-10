'use client'

import { SigningClient } from '@apex/crypto-client'
import type { SigningKey } from '@apex/shared-types/contracts'
import { Badge, Button, Dialog, DialogClose, DialogContent, Icon, SigningSeal, Table, type TableColumn } from '@apex/ui'
import { useQueryClient } from '@tanstack/react-query'
import { CircleOff, Fingerprint, KeyRound, MonitorX, Plus, ShieldAlert } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { useEffect, useState } from 'react'

import { renderLink } from '@/components/app-link'
import { api, ApiError } from '@/lib/api'
import { enrollKeyFor, openSigningSessionFor, revokeKeyFor } from '@/lib/signing/connect'
import { signingView } from '@/lib/signing/countdown'
import { startStepUp } from '@/lib/signing/step-up'
import { signingKeysKey, useMySigningKeys } from '@/lib/signing/use-keys'
import { useSigningSession } from '@/stores/signing-session'

type Support = 'checking' | 'yes' | 'no'

/** Short public fingerprint: the key is public, the table only needs to tell keys apart. */
const fingerprint = (k: SigningKey) => `ed25519:${k.public_key.slice(0, 6)}…${k.public_key.slice(-4)}`

export function SigningView({ userId, role }: { userId: string | null; role: string }) {
  const t = useTranslations('signing')
  const [support, setSupport] = useState<Support>('checking')
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState<SigningKey | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Set only after the API confirmed the signed revocation; it is what plays the seal.
  const [sealed, setSealed] = useState<{ fingerprint: string; hash: string } | null>(null)
  const locale = useLocale()
  const queryClient = useQueryClient()
  const keysQuery = useMySigningKeys()
  const keys = keysQuery.data?.items ?? []
  const { session, offsetMs } = useSigningSession()
  const sessionLive = session !== null && signingView(session, Date.now(), offsetMs) === 'active'

  const run = async (action: () => Promise<void>, close?: () => void) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      close?.()
    } catch (e) {
      // A 428 already sent the browser to the step-up (client.ts); nothing is signed or retried silently here.
      if (!(e instanceof ApiError && e.status === 428)) setError(e instanceof Error ? e.message : t('errorGeneric'))
    } finally {
      setBusy(false)
    }
  }
  const refresh = () => queryClient.invalidateQueries({ queryKey: signingKeysKey })

  // #144: la comprobación genera una clave efímera no exportable y la descarta; nunca hay clave en servidor.
  useEffect(() => {
    void SigningClient.isSupported().then((ok) => setSupport(ok ? 'yes' : 'no'))
  }, [])

  const viewer = role === 'viewer'
  // Motivo visible de por qué no se puede firmar (rol primero, luego navegador).
  const blocked = viewer ? t('viewerReason') : support === 'no' ? t('unsupportedReason') : !userId ? t('noUser') : undefined
  const needSession = blocked ?? (sessionLive ? undefined : t('needSession'))
  const date = (iso: string) => new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(iso))

  const columns: TableColumn<SigningKey>[] = [
    { id: 'device', header: t('colDevice'), sortable: false, cell: (k) => k.label ?? k.id },
    { id: 'key', header: t('colKey'), sortable: false, cell: (k) => <span className="font-mono">{fingerprint(k)}</span> },
    { id: 'created', header: t('colCreated'), sortable: false, cell: (k) => date(k.created_at) },
    {
      id: 'status',
      header: t('colStatus'),
      sortable: false,
      cell: (k) =>
        k.revoked_at == null ? <Badge tone="ok">{t('active')}</Badge> : <Badge tone="neutro" icon={CircleOff}>{t('revoked')}</Badge>,
    },
    {
      id: 'action',
      header: t('colAction'),
      hidden: true,
      num: true,
      cell: (k) =>
        k.revoked_at == null ? (
          <Button size="sm" {...(needSession ? { disabledReason: needSession } : {})} onClick={() => setRevoking(k)}>
            <Icon icon={CircleOff} />
            {t('revoke')}
          </Button>
        ) : (
          <span className="text-ink-muted">{t('revokedNote')}</span>
        ),
    },
  ]

  return (
    <div className="flex flex-col gap-8 px-(--gutter-page) py-6">
      <header>
        <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
        <p className="mt-1.5 text-ink-soft">{t('intro')}</p>
      </header>

      {viewer ? (
        <div role="status" className="flex items-start gap-2 border border-line bg-panel p-4">
          <Icon icon={ShieldAlert} />
          <div>
            <strong>{t('viewerTitle')}</strong>
            <p className="m-0 text-ink-soft">{t('viewerBody')}</p>
          </div>
        </div>
      ) : null}

      {support === 'no' ? (
        <div role="alert" className="flex items-start gap-2 border border-bad bg-bad-subtle p-4">
          <Icon icon={MonitorX} />
          <div>
            <strong className="text-bad">{t('unsupportedTitle')}</strong>
            <p className="my-1">{t('unsupportedBody')}</p>
            <p className="m-0 text-ink-muted">{t('unsupportedNever')}</p>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-10">
        <section className="flex min-w-0 flex-[1_1_400px] flex-col gap-3">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
            <Icon icon={KeyRound} />
            {t('keyHeading')}
          </h2>
          <div className="flex flex-col gap-3 border border-line bg-panel p-4">
            <p className="m-0">{t('keyIntro')}</p>
            <div className="flex gap-4">
              <span className="text-ink-muted">{t('browser')}</span>
              <span>{support === 'checking' ? t('checking') : support === 'yes' ? t('browserOk') : t('unsupportedReason')}</span>
            </div>
            <div>
              <Button variant="pri" {...(blocked ? { disabledReason: blocked } : {})} onClick={() => setCreating(true)}>
                <Icon icon={Plus} />
                {t('createOpen')}
              </Button>
            </div>
            <p className="m-0 text-ink-muted">{t('createNote')}</p>
          </div>
        </section>

        <section className="flex min-w-0 flex-[1_1_400px] flex-col gap-3">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
            <Icon icon={Fingerprint} />
            {t('sessionHeading')}
          </h2>
          <div className="flex flex-col gap-3 border border-line bg-panel p-4">
            <p className="m-0">{t('sessionBody')}</p>
            <p className="m-0 text-ink-muted">
              {session && sessionLive ? t('sessionLive', { count: session.remaining_decisions }) : t('sessionNone')}
            </p>
            <div className="flex gap-2">
              {/* Strong auth first (Keycloak step-up); the window opens with the fresh token. */}
              <Button
                variant="pri"
                {...(blocked ? { disabledReason: blocked } : {})}
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    if (!(await startStepUp()) || !userId) throw new Error(t('stepUpFailed'))
                    await openSigningSessionFor(userId)
                    await refresh()
                  })
                }
              >
                <Icon icon={Fingerprint} />
                {t('sessionOpen')}
              </Button>
              {session && sessionLive ? (
                <Button
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      useSigningSession.getState().setSession(await api.closeSigningSession(session.id), Date.now())
                    })
                  }
                >
                  {t('sessionClose')}
                </Button>
              ) : null}
            </div>
          </div>
        </section>
      </div>

      {error ? (
        <p role="alert" className="m-0 border border-bad bg-bad-subtle p-3 text-bad">
          {error}
        </p>
      ) : null}

      {sealed ? (
        <SigningSeal playing role="status" className="border border-line bg-panel p-4">
          <strong>{t('sealedTitle')}</strong>
          <p className="my-1 font-mono">{sealed.fingerprint}</p>
          <p className="ap-hash m-0 break-all font-mono text-ink-muted">{sealed.hash}</p>
        </SigningSeal>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
          <Icon icon={KeyRound} />
          {t('keysHeading')}
        </h2>
        {keysQuery.isError ? (
          <p role="alert" className="m-0 text-bad">
            {t('keysError')}
          </p>
        ) : null}
        <Table columns={columns} rows={keys} getRowId={(k) => k.id} caption={t('keysHeading')} empty={keysQuery.isPending ? t('checking') : t('keysEmpty')} renderLink={renderLink} />
      </section>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent title={t('createTitle')} description={t('keyIntro')} closeLabel={t('close')}>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button>{t('cancel')}</Button>
            </DialogClose>
            <Button
              variant="pri"
              disabled={busy}
              {...(blocked ? { disabledReason: blocked } : {})}
              onClick={() =>
                void run(async () => {
                  await enrollKeyFor(userId!)
                  await refresh()
                }, () => setCreating(false))
              }
            >
              {t('createConfirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={revoking !== null} onOpenChange={(o) => !o && setRevoking(null)}>
        <DialogContent title={t('revokeTitle')} description={t('revokeBody')} closeLabel={t('close')}>
          <p className="font-mono">{revoking ? fingerprint(revoking) : null}</p>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button>{t('cancel')}</Button>
            </DialogClose>
            <Button
              variant="danger"
              disabled={busy}
              {...(needSession ? { disabledReason: needSession } : {})}
              onClick={() =>
                revoking &&
                void run(async () => {
                  const { decision } = await revokeKeyFor(userId!, revoking.id)
                  setSealed({ fingerprint: fingerprint(revoking), hash: decision.payload_hash })
                  await refresh()
                }, () => setRevoking(null))
              }
            >
              {t('revokeConfirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
