'use client'

import { SigningClient } from '@apex/crypto-client'
import { Badge, Button, Dialog, DialogClose, DialogContent, Icon, Table, type TableColumn } from '@apex/ui'
import { CircleOff, Fingerprint, KeyRound, MonitorX, Plus, ShieldAlert } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useEffect, useState } from 'react'

import { renderLink } from '@/components/app-link'
import type { KeyFixture } from '@/fixtures/signing-keys'

type Support = 'checking' | 'yes' | 'no'

export function SigningView({ keys, role }: { keys: KeyFixture[]; role: string }) {
  const t = useTranslations('signing')
  const [support, setSupport] = useState<Support>('checking')
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState<KeyFixture | null>(null)

  // #144: la comprobación genera una clave efímera no exportable y la descarta; nunca hay clave en servidor.
  useEffect(() => {
    void SigningClient.isSupported().then((ok) => setSupport(ok ? 'yes' : 'no'))
  }, [])

  const viewer = role === 'viewer'
  // Motivo visible de por qué no se puede firmar (rol primero, luego navegador).
  const blocked = viewer ? t('viewerReason') : support === 'no' ? t('unsupportedReason') : undefined
  const pending = t('pending')

  const columns: TableColumn<KeyFixture>[] = [
    { id: 'device', header: t('colDevice'), sortable: false, cell: (k) => k.device },
    { id: 'key', header: t('colKey'), sortable: false, cell: (k) => <span className="font-mono">{k.fingerprint}</span> },
    { id: 'created', header: t('colCreated'), sortable: false, cell: (k) => k.createdAt },
    {
      id: 'status',
      header: t('colStatus'),
      sortable: false,
      cell: (k) =>
        k.status === 'active' ? <Badge tone="ok">{t('active')}</Badge> : <Badge tone="neutro" icon={CircleOff}>{t('revoked')}</Badge>,
    },
    {
      id: 'action',
      header: t('colAction'),
      hidden: true,
      num: true,
      cell: (k) =>
        k.status === 'active' ? (
          <Button size="sm" {...(blocked ? { disabledReason: blocked } : {})} onClick={() => setRevoking(k)}>
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
            <p className="m-0 text-ink-muted">{t('sessionNone')}</p>
            <div>
              {/* //todo_#150: abrir la sesión de firma con passkey (POST /v1/signing-sessions) */}
              <Button variant="pri" disabledReason={blocked ?? pending}>
                <Icon icon={Fingerprint} />
                {t('sessionOpen')}
              </Button>
            </div>
          </div>
        </section>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
          <Icon icon={KeyRound} />
          {t('keysHeading')}
        </h2>
        <Table columns={columns} rows={keys} getRowId={(k) => k.id} caption={t('keysHeading')} empty={t('keysEmpty')} renderLink={renderLink} />
      </section>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent title={t('createTitle')} description={t('keyIntro')} closeLabel={t('close')}>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button>{t('cancel')}</Button>
            </DialogClose>
            {/* //todo_#149: generar la clave no exportable y registrarla (POST /v1/keys/me); aquí no se crea ninguna */}
            <Button variant="pri" disabledReason={pending}>
              {t('createConfirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={revoking !== null} onOpenChange={(o) => !o && setRevoking(null)}>
        <DialogContent title={t('revokeTitle')} description={t('revokeBody')} closeLabel={t('close')}>
          <p className="font-mono">{revoking?.fingerprint}</p>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button>{t('cancel')}</Button>
            </DialogClose>
            {/* //todo_#149: revocar con passkey (POST /v1/keys/{id}/revoke) */}
            <Button variant="danger" disabledReason={pending}>
              {t('revokeConfirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
