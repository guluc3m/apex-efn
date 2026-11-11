'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'

import { useViewer } from '@/components/viewer-context'
import { ApiError } from '@/lib/api'

import { signDecisionFor } from './connect'
import { SigningUnsupportedError } from './open-session'
import { NoSigningSessionError, PayloadMismatchError } from './sign-decision'

/** Signs an existing pending decision with the browser key. The message is already translated. */
export function useSignDecision() {
  const t = useTranslations('signing.signFlow')
  const { userId } = useViewer()
  const qc = useQueryClient()
  const mutation = useMutation({
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approvals'] }),
    mutationFn: (decisionId: string) => {
      if (!userId) throw new NoSigningSessionError()
      return signDecisionFor(userId, decisionId)
    },
  })
  const e = mutation.error
  const message = !e
    ? null
    : e instanceof NoSigningSessionError
      ? t('noSession')
      : e instanceof SigningUnsupportedError
        ? t('unsupported')
        : e instanceof PayloadMismatchError
          ? t('mismatch')
          : e instanceof ApiError && e.status === 428
            ? null // the global step-up handler already took over
            : e instanceof ApiError
              ? e.title
              : t('failed')
  return { sign: mutation.mutate, signing: mutation.isPending, signed: mutation.isSuccess, message, reset: mutation.reset }
}
