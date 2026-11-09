'use client'

import { ErrorPanel } from '@/components/error-panel'

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorPanel kind="error" onRetry={reset} />
}
