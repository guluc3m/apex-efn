import { Ban, Wallet, WalletMinimal, type LucideIcon } from 'lucide-react'

import { StatusBadge, type StatusTone } from './status-badge.js'

export type FinancialVerdict = 'within_budget' | 'stretch' | 'out_of_budget'

const FINANCIAL_VERDICT: Record<FinancialVerdict, { tone: StatusTone; icon: LucideIcon }> = {
  within_budget: { tone: 'ok', icon: Wallet },
  stretch: { tone: 'warn', icon: WalletMinimal },
  out_of_budget: { tone: 'bad', icon: Ban },
}

export interface FinancialVerdictBadgeProps {
  verdict: FinancialVerdict
  label: string
}

/** Veredicto de encaje financiero (DESIGN §6). */
export function FinancialVerdictBadge({ verdict, label }: FinancialVerdictBadgeProps) {
  const v = FINANCIAL_VERDICT[verdict]
  return <StatusBadge tone={v.tone} icon={v.icon} label={label} />
}
