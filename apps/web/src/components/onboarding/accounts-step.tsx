'use client'

import { Badge, Button, Icon, Input, Label } from '@apex/ui'
import { LogIn, Plug, Save, Unplug } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

import type { Platform } from '@/fixtures/onboarding'

const th = 'border-b border-line px-3 py-2 text-left text-[13px] font-normal text-ink-muted'
const td = 'border-b border-line px-3 py-2'

/**
 * Cuentas de plataformas. Reutilizable (`/empresa/cuentas`).
 * Las credenciales viven solo en los inputs del DOM: sin estado, sin store, sin onChange.
 */
export function AccountsStep({ platforms }: { platforms: Platform[] }) {
  const t = useTranslations('onboarding.accounts')
  const [connecting, setConnecting] = useState<Platform | null>(null)
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
          {platforms.map((p) => (
            <tr key={p.id}>
              <th scope="row" className={`${td} text-left font-normal`}>{p.name}</th>
              <td className={`${td} text-[13px] text-ink-muted`}>{t(`connections.${p.connection}`)}</td>
              <td className={td}>
                {p.state === 'connected' && <Badge tone="ok">{t('states.connected')}</Badge>}
                {p.state === 'expired' && <Badge tone="warn">{t('states.expired')}</Badge>}
                {p.state === 'none' && <Badge tone="neutro" icon={Unplug}>{t('states.none')}</Badge>}
              </td>
              <td className={`${td} text-right`}>
                {/* //todo_#154: desconectar la cuenta en el almacén cifrado */}
                {p.state === 'connected' && (
                  <Button variant="ghost" size="sm" disabledReason={t('pending')}>
                    <Icon icon={Unplug} />
                    {t('disconnect')}
                  </Button>
                )}
                {p.state !== 'connected' && (
                  <Button variant="sec" size="sm" onClick={() => setConnecting(p)}>
                    <Icon icon={p.state === 'expired' ? LogIn : Plug} />
                    {p.state === 'expired' ? t('relogin') : t('connect')}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {connecting && (
        <form key={connecting.id} className="flex flex-col gap-3 border border-line bg-panel p-4" onSubmit={(e) => e.preventDefault()} autoComplete="off">
          <strong className="font-semibold">{t('connectTitle', { name: connecting.name })}</strong>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="acc-user">{t('user')}</Label>
              <Input id="acc-user" name="user" autoComplete="off" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="acc-pass">{t('password')}</Label>
              <Input id="acc-pass" name="pass" type="password" autoComplete="off" />
            </div>
          </div>
          <p className="m-0 text-[13px] text-ink-muted">{t('vaultNote')}</p>
          <div>
            {/* //todo_#154: enviar las credenciales directo al almacén cifrado; nunca a estado de cliente */}
            <Button type="button" variant="pri" disabledReason={t('pending')}>
              <Icon icon={Save} />
              {t('save')}
            </Button>
          </div>
        </form>
      )}
    </>
  )
}
