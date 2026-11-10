/**
 * Ports for the browser pool. A driver launches browsers; a browser hands out pages. Adapters never talk to
 * Chrome directly, which keeps the pool testable without a real browser and keeps every launch (proxy, flags,
 * recycling) in one place.
 */

export interface BrowserPage {
  /** Stable id for logs and metrics. Never a URL, a cookie or a credential. */
  readonly id: string
  close(): Promise<void>
}

export interface BrowserHandle {
  readonly id: string
  newPage(): Promise<BrowserPage>
  close(): Promise<void>
  /** Resident memory of the browser process in MB, or `null` when the driver cannot measure it. */
  memoryMb(): number | null
  /** `false` once Chrome crashed or was killed; the pool then stops handing out its pages. */
  isConnected(): boolean
}

export interface LaunchOptions {
  /** Proxy URL resolved for the account, or `null`. Credentials are redacted before anything is logged. */
  proxyUrl: string | null
}

export interface BrowserDriver {
  launch(options: LaunchOptions): Promise<BrowserHandle>
}
