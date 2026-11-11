'use client'

import { Badge, Button, Icon, Input, Label } from '@apex/ui'
import { Plug, Save, Unplug } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

import { ApiError, useAccountAction, useConnectedAccounts } from '@/lib/api'

const th = 'border-b border-line px-3 py-2 text-left text-[13px] font-normal text-ink-muted'
const td = 'border-b border-line px-3 py-2'

/**
 * Cuentas de plataformas (`/empresa/cuentas` y el asistente).
 * Las credenciales viven solo en los inputs del DOM: se leen del formulario al enviar, directo al
 * servidor (que las guarda en el almacén cifrado), sin estado, sin store, sin onChange.
 */
export function AccountsStep() {
  const t = useTranslations('onboarding.accounts')
  const accounts = useConnectedAccounts()
  const act = useAccountAction()
  const [connecting, setConnecting] = useState<string | null>(null)

  if (accounts.isPending) return <p role="status" className="m-0 text-ink-muted">{t('loading')}</p>
  if (accounts.isError) {
    const forbidden = accounts.error instanceof ApiError && accounts.error.status === 403
    return <p role="alert" className="m-0 text-bad">{forbidden ? t('forbidden') : t('connectFailed')}</p>
  }

  const byPlatform = new Map(accounts.data.items.map((a) => [a.platform, a]))
  const reason = act.error instanceof ApiError && act.error.reason === 'vault_unavailable' ? t('vault_unavailable') : t('connectFailed')

  return (
    <>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className={th}>{t('platform')}</th>
            <th className={th}>{t('connection')}</th>
            <th className={th}>{t('status')}</th>
            <th className={`${th} text-right`}>{t('action')}</th>
          </tr>
        </thead>
        <tbody>
          {accounts.data.platforms.map((id) => {
            const acc = byPlatform.get(id)
            const live = acc?.status === 'active'
            return (
              <tr key={id}>
                <th scope="row" className={`${td} text-left font-normal`}>{id}</th>
                <td className={`${td} text-[13px] text-ink-muted`}>{t('connections.password')}</td>
                <td className={td}>
                  {live && <Badge tone="ok">{t('states.connected')}</Badge>}
                  {acc && !live && <Badge tone="warn">{t('states.expired')}</Badge>}
                  {!acc && <Badge tone="neutro" icon={Unplug}>{t('states.none')}</Badge>}
                </td>
                <td className={`${td} text-right`}>
                  {acc && (
                    <Button variant="ghost" size="sm" disabled={act.isPending} onClick={() => act.mutate({ disconnect: acc.id })}>
                      <Icon icon={Unplug} />
                      {t('disconnect')}
                    </Button>
                  )}{' '}
                  <Button variant="sec" size="sm" onClick={() => { act.reset(); setConnecting(id) }}>
                    <Icon icon={Plug} />
                    {acc && !live ? t('relogin') : t('connect')}
                  </Button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {connecting && (
        <form
          key={connecting}
          className="flex flex-col gap-3 border border-line bg-panel p-4"
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault()
            const form = e.currentTarget
            const data = new FormData(form)
            act.mutate(
              { connect: { platform: connecting, username: (data.get('user') as string | null) ?? '', password: (data.get('pass') as string | null) ?? '' } },
              { onSuccess: () => { form.reset(); setConnecting(null) } },
            )
          }}
        >
          <strong className="font-semibold">{t('connectTitle', { name: connecting })}</strong>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="acc-user">{t('user')}</Label>
              <Input id="acc-user" name="user" autoComplete="off" required />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="acc-pass">{t('password')}</Label>
              <Input id="acc-pass" name="pass" type="password" autoComplete="off" required />
            </div>
          </div>
          <p className="m-0 text-[13px] text-ink-muted">{t('vaultNote')}</p>
          {act.isError && <p role="alert" className="m-0 text-[13px] text-bad">{reason}</p>}
          <div>
            <Button type="submit" variant="pri" disabled={act.isPending}>
              <Icon icon={Save} />
              {t('save')}
            </Button>
          </div>
        </form>
      )}
    </>
  )
}
