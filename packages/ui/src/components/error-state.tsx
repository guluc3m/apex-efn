import { OctagonAlert } from 'lucide-react'

import { cn } from '../lib/utils.js'

import { Button } from './button.js'
import { Icon } from './icon.js'

export interface ErrorStateProps {
  /** `title` del problem+json. */
  title: string
  /** `detail` del problem+json, sin traducir lo que el servidor ya dice. */
  detail?: string
  retryLabel?: string
  onRetry?: () => void
  /** Identificador de traza que soporte puede buscar. Se muestra en mono. */
  trace?: string
  className?: string
}

/** Error de carga (DESIGN §6): title y detail del problem+json y «Reintentar». `428` no pasa por aquí. */
export function ErrorState({
  title,
  detail,
  retryLabel,
  onRetry,
  trace,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn('border-bad-subtle bg-bad-subtle box-border border p-6', className)}
    >
      <strong className="text-bad flex items-center gap-2.5 font-semibold">
        <Icon icon={OctagonAlert} size={20} />
        {title}
      </strong>
      {detail && <p className="text-ink m-0 mt-1">{detail}</p>}
      {(onRetry || trace) && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {onRetry && retryLabel && (
            <Button variant="sec" onClick={onRetry}>
              {retryLabel}
            </Button>
          )}
          {trace && <span className="text-ink-muted font-mono text-[13px]">{trace}</span>}
        </div>
      )}
    </div>
  )
}
