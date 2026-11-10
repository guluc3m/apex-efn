/**
 * Proxy resolution (D5-02b).
 *
 * The pool asks for one URL per launch. Which family is used, and whether an account has its own proxy, is a
 * deployment decision that lives here rather than in the pool: the pool never sees a credential, only the URL it
 * was handed. Per-account allocations from Vault are the next step; this resolver already takes overrides so the
 * wiring does not change when that lands.
 */

export type ProxyFamily = 'residential' | 'datacenter'

export interface AccountProxy {
  url: string
  family?: ProxyFamily
}

export interface StaticProxyOptions {
  residentialUrl?: string | undefined
  datacenterUrl?: string | undefined
  /** Family used when the account has no override. Defaults to `residential`. */
  family?: ProxyFamily
  /** Per-account overrides, keyed by the opaque account id. */
  perAccount?: Record<string, AccountProxy>
}

export interface ProxyResolver {
  resolve(accountId: string | null): Promise<string | null>
}

/**
 * Resolves from configuration: an account override first, then the configured family, then the other family when
 * the preferred one is unset. `null` means "no proxy", never "use whatever is lying around".
 */
export class StaticProxyResolver implements ProxyResolver {
  constructor(private readonly options: StaticProxyOptions) {}

  resolve(accountId: string | null): Promise<string | null> {
    if (accountId !== null) {
      const override = this.options.perAccount?.[accountId]
      if (override !== undefined) {
        return Promise.resolve(override.url)
      }
    }
    const preferred = this.options.family ?? 'residential'
    const chosen =
      preferred === 'datacenter'
        ? this.options.datacenterUrl ?? this.options.residentialUrl
        : this.options.residentialUrl ?? this.options.datacenterUrl
    return Promise.resolve(chosen ?? null)
  }
}
