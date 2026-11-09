import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  ShieldX,
  type LucideIcon,
} from 'lucide-react'
import type * as React from 'react'

import { StatusBadge, type StatusTone } from './status-badge.js'

export type ConfidenceBand = 'high' | 'medium' | 'low' | 'untrusted' | 'insufficient_data'

const CONFIDENCE_BAND: Record<ConfidenceBand, { tone: StatusTone; icon: LucideIcon }> = {
  high: { tone: 'ok', icon: ShieldCheck },
  medium: { tone: 'neutro', icon: Shield },
  low: { tone: 'warn', icon: ShieldAlert },
  untrusted: { tone: 'bad', icon: ShieldX },
  insufficient_data: { tone: 'neutro', icon: ShieldQuestion },
}

export interface ConfidenceBandBadgeProps {
  band: ConfidenceBand
  label: string
  /** Desglose de señales y model_version, ya renderizado por el llamador. */
  breakdown?: React.ReactNode
  breakdownTitle?: string
}

/** Confianza del vendedor (DESIGN §6). Con `breakdown` abre el porqué en un Popover. */
export function ConfidenceBandBadge({
  band,
  label,
  breakdown,
  breakdownTitle,
}: ConfidenceBandBadgeProps) {
  const v = CONFIDENCE_BAND[band]
  return (
    <StatusBadge
      tone={v.tone}
      icon={v.icon}
      label={label}
      breakdown={breakdown}
      breakdownTitle={breakdownTitle}
    />
  )
}
