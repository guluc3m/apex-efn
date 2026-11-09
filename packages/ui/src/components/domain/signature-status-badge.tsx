import { BadgeAlert, BadgeCheck, Clock, type LucideIcon } from 'lucide-react'

import { StatusBadge, type StatusTone } from './status-badge.js'

export type SignatureStatus = 'signed' | 'pending' | 'invalid'

const SIGNATURE_STATUS: Record<SignatureStatus, { tone: StatusTone; icon: LucideIcon }> = {
  signed: { tone: 'ok', icon: BadgeCheck },
  pending: { tone: 'neutro', icon: Clock },
  invalid: { tone: 'bad', icon: BadgeAlert },
}

export interface SignatureStatusBadgeProps {
  status: SignatureStatus
  label: string
}

/** Estado de firma de una decisión (DESIGN §6). */
export function SignatureStatusBadge({ status, label }: SignatureStatusBadgeProps) {
  const v = SIGNATURE_STATUS[status]
  return <StatusBadge tone={v.tone} icon={v.icon} label={label} />
}
