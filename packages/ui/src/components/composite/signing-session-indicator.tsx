import { Fingerprint, History, OctagonAlert, PenLine } from 'lucide-react'
import * as React from 'react'

import { cn } from '../../lib/utils.js'
import { Badge } from '../badge.js'
import { buttonVariants } from '../button.js'
import { Icon } from '../icon.js'

import { anchor, type RenderLink } from './link.js'

export type SigningSessionState = 'none' | 'active' | 'expiring' | 'expired' | 'exhausted'

export interface SigningSessionLabels {
  signing: string
  noSession: string
  expiring: string
  expired: string
  exhausted: string
  openSession: string
  reauth: string
  /** «Tiempo restante: 12:34» a partir de `mm:ss`. */
  timerLabel: (time: string) => string
}

export interface SigningSessionIndicatorProps {
  /** Instante de caducidad fijo (ISO o ms): la ventana no se desliza. Sin él, no hay sesión. */
  expiresAt?: string | number | undefined
  /** Reloj inyectado (ms) para pruebas; sin él, se actualiza cada segundo. */
  now?: number
  signer?: string
  /** Texto ya formateado: «7 firmas». */
  signaturesLabel?: string
  signaturesLeft?: number
  labels: SigningSessionLabels
  /** Abre o reabre la sesión (flujo de passkey). */
  action: { href: string }
  renderLink?: RenderLink
  /** Una sola vez al pasar a caducada, para dejar la vista en solo lectura sin recargar. */
  onExpire?: () => void
  className?: string
}

const WARN_MS = 60_000

export function formatRemaining(ms: number): string {
  const s = Math.max(0, Math.ceil(ms / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function SigningSessionIndicator({ expiresAt, now, signer, signaturesLabel, signaturesLeft, labels, action, renderLink = anchor, onExpire, className }: SigningSessionIndicatorProps) {
  const [tick, setTick] = React.useState<number | null>(null)
  React.useEffect(() => {
    if (now !== undefined || expiresAt === undefined) return
    setTick(Date.now())
    const id = setInterval(() => setTick(Date.now()), 1000)
    return () => clearInterval(id)
  }, [now, expiresAt])

  const at = expiresAt === undefined ? undefined : new Date(expiresAt).getTime()
  const clock = now ?? tick
  // Primer render sin hora: placeholder estable para no romper la hidratación.
  const left = at === undefined || clock === null ? 0 : at - clock
  const state: SigningSessionState =
    at === undefined ? 'none' : clock === null ? 'active' : left <= 0 ? 'expired' : signaturesLeft === 0 ? 'exhausted' : left <= WARN_MS ? 'expiring' : 'active'

  const wasExpired = React.useRef(false)
  React.useEffect(() => {
    if (state === 'expired' && !wasExpired.current) onExpire?.()
    wasExpired.current = state === 'expired'
  }, [state, onExpire])

  const dead = state === 'expired' || state === 'exhausted'
  const time = clock === null ? '--:--' : formatRemaining(left)
  const announce = { expiring: labels.expiring, expired: labels.expired, exhausted: labels.exhausted, active: '', none: '' }[state]
  const cta = (text: string) =>
    renderLink({
      href: action.href,
      className: buttonVariants({ variant: 'pri', size: 'sm', state: 'ready' }),
      children: (
        <>
          <Icon icon={Fingerprint} />
          {text}
        </>
      ),
    })

  return (
    <div className={cn('inline-flex min-h-9.5 flex-wrap items-center gap-3 border border-line bg-panel py-1', state === 'none' || dead ? 'pr-1 pl-3' : 'px-3', className)}>
      <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-muted">
        <Icon icon={PenLine} />
        {labels.signing}
      </span>
      <span role="status" className="sr-only">{announce}</span>
      {state === 'none' && <span className="text-[13px] text-ink-muted">{labels.noSession}</span>}
      {state !== 'none' && signer && <span>{signer}</span>}
      {(state === 'active' || state === 'expiring') && (
        <>
          <strong role="timer" aria-label={labels.timerLabel(time)} className={cn('font-semibold tabular-nums', state === 'expiring' && 'text-warn')}>{time}</strong>
          {signaturesLabel && <span className="text-[13px] text-ink-muted">{signaturesLabel}</span>}
          {state === 'expiring' && <Badge tone="warn" icon={History}>{labels.expiring}</Badge>}
        </>
      )}
      {dead && <Badge tone="bad" icon={OctagonAlert}>{state === 'exhausted' ? labels.exhausted : labels.expired}</Badge>}
      {state === 'none' ? cta(labels.openSession) : dead ? cta(labels.reauth) : null}
    </div>
  )
}
