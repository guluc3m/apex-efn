'use client'

import { ErrorState, Skeleton } from '@apex/ui'
import type { UseQueryResult } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import type { ReactNode } from 'react'

import { ApiError } from '@/lib/api'

/** Loading skeleton, error with retry, or the data. Problem title/detail come from the server as is. */
export function QueryBoundary<T>({ query, children }: { query: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  const t = useTranslations('common.query')
  if (query.isPending)
    return (
      <div role="status" aria-label={t('loading')} className="flex flex-col gap-2">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-2/3" />
      </div>
    )
  if (query.isError) {
    const e = query.error
    return (
      <ErrorState
        title={e instanceof ApiError ? e.title : t('error')}
        detail={e instanceof ApiError ? e.detail : undefined}
        retryLabel={t('retry')}
        onRetry={() => void query.refetch()}
      />
    )
  }
  return <>{children(query.data)}</>
}
