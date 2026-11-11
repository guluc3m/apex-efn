'use client'

import { Button, Icon } from '@apex/ui'
import { PenLine } from 'lucide-react'
import { useTranslations } from 'next-intl'
import type { ReactNode } from 'react'

import { useSignDecision } from '@/lib/signing/use-sign-decision'

/**
 * Signs a pending decision with the browser key. Without a `decisionId` it is disabled with `reasonWithout`.
 * Nothing is shown as signed until the API accepts the signature.
 */
export function SignDecisionButton({ decisionId, reasonWithout, children }: { decisionId?: string; reasonWithout: string; children: ReactNode }) {
  const t = useTranslations('signing.signFlow')
  const { sign, signing, signed, message } = useSignDecision()
  return (
    <>
      <Button
        variant="pri"
        disabledReason={!decisionId ? reasonWithout : signed ? t('signed') : signing ? t('signing') : undefined}
        onClick={() => decisionId && sign(decisionId)}
      >
        <Icon icon={PenLine} />
        {children}
      </Button>
      {message ? (
        <p role="alert" className="m-0 text-bad">
          {message}
        </p>
      ) : null}
      {signed ? (
        <p role="status" className="m-0">
          {t('signed')}
        </p>
      ) : null}
    </>
  )
}
