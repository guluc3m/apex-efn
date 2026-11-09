import { History, Info, WifiOff, type LucideIcon } from 'lucide-react'

import { StatusBadge } from './status-badge.js'

export type EdgeWarning = 'fx_provisional' | 'financials_stale' | 'live_connection_lost'

const ICON: Record<EdgeWarning, LucideIcon> = {
  fx_provisional: Info,
  financials_stale: History,
  live_connection_lost: WifiOff,
}

export interface EdgeWarningBadgeProps {
  kind: EdgeWarning
  label: string
  /** El porqué: tasa usada y antigüedad, fecha del último CSV, desde cuándo no hay conexión. */
  explanation?: React.ReactNode
  explanationTitle?: string
}

/** Avisos de borde (DESIGN §6): siempre `warning`, con su icono y su texto. */
export function EdgeWarningBadge({
  kind,
  label,
  explanation,
  explanationTitle,
}: EdgeWarningBadgeProps) {
  return (
    <StatusBadge
      tone="warn"
      icon={ICON[kind]}
      label={label}
      breakdown={explanation}
      breakdownTitle={explanationTitle}
    />
  )
}
