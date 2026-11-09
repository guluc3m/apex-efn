/**
 * Starts the browser worker when `NEXT_PUBLIC_API_MOCKING=enabled`. Off by default and never on in
 * production builds, so a deployed UI cannot silently answer from fixtures.
 */
export async function enableApiMocking(): Promise<void> {
  if (process.env.NODE_ENV === 'production') return
  if (process.env.NEXT_PUBLIC_API_MOCKING !== 'enabled') return
  if (typeof window === 'undefined') return
  const { worker } = await import('./browser')
  await worker.start({ onUnhandledRequest: 'bypass', quiet: true })
}
