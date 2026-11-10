'use client'

import type { DecisionAccepted } from '@apex/shared-types/contracts'
import { Button, Icon } from '@apex/ui'
import { FilePlus2, PenLine, X } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { ApiError } from '@/lib/api'

/**
 * Footer of every action dialog. "Create decision" calls the API and leaves it pending signature.
 * "Sign" stays disabled until the signing flow (POST /v1/decisions/{id}/sign, D2-09) exists: this
 * screen never fakes a signature.
 */
export function DecisionFooter({
  disabledReason,
  busy,
  error,
  accepted,
  onCreate,
  onClose,
}: {
  /** Why creating is not possible yet (role, incomplete form); undefined when it is. */
  disabledReason?: string
  busy: boolean
  error: unknown
  accepted?: DecisionAccepted
  onCreate: () => void
  onClose: () => void
}) {
  const t = useTranslations('decisions.dialog')
  return (
    <>
      {error !== null && error !== undefined && (
        <p role="alert" className="mb-3 text-bad">
          {error instanceof ApiError ? `${error.title}${error.detail ? `: ${error.detail}` : ''}` : t('error')}
        </p>
      )}
      {accepted && (
        <p role="status" className="mb-3 text-ink-soft">
          {t('created', { id: accepted.decision_id })}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {!accepted && (
          <Button variant="sec" disabledReason={disabledReason ?? (busy ? t('creating') : undefined)} onClick={onCreate}>
            <Icon icon={FilePlus2} />
            {t('create')}
          </Button>
        )}
        <Button variant="pri" disabledReason={t('signUnavailable')}>
          <Icon icon={PenLine} />
          {t('sign')}
        </Button>
        <Button onClick={onClose}>
          <Icon icon={X} />
          {accepted ? t('close') : t('cancel')}
        </Button>
      </div>
    </>
  )
}
