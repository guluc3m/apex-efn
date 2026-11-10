/**
 * Platform adapters. Each adapter reads one platform and returns RAW data: listed prices, raw seller signals and
 * raw chat text. Normalisation, FX, confidence and bands belong to the orchestrator (spec 3.4.1).
 */

import type {
  ChatRole,
  PlatformStatus,
  RawOffer,
  RawSeller,
  RawSellerSignals,
  SkippedListing,
} from '@apex/shared-types/contracts/browser-worker'

import { WorkerError } from '../errors.js'
import type { FlagProvider } from '../platform/flags.js'
import { platformFlagName } from '../platform/flags.js'

export type TransportType = PlatformStatus['transport']

export interface SearchInput {
  query: string
  quantity: number | null
  maxResults: number
}

export interface SearchOutput {
  offers: RawOffer[]
  skipped: SkippedListing[]
  truncated: boolean
}

export interface ChatOpenInput {
  accountId: string
  platformSellerId: string
  productId: string
}

export interface ChatMessageRecord {
  seq: number
  role: ChatRole
  text: string
  at: Date
}

export interface ChatAdapter {
  open(input: ChatOpenInput): Promise<{ platformChatId: string }>
  send(platformChatId: string, text: string): Promise<{ platformSeq: number; at: Date }>
  read(platformChatId: string, afterSeq: number): Promise<ChatMessageRecord[]>
  screenshot(platformChatId: string): Promise<Uint8Array>
}

export interface PlatformAdapter {
  readonly platform: string
  readonly transport: TransportType
  search(input: SearchInput): Promise<SearchOutput>
  getProduct(platformOfferId: string): Promise<RawOffer>
  getSeller(platformSellerId: string): Promise<RawSeller>
  getSellerSignals(
    platformSellerId: string,
    options: { maxReviews: number }
  ): Promise<RawSellerSignals>
  chat?: ChatAdapter
}

/**
 * Looks up adapters by platform id. A disabled platform (flag `platform.<id>.enabled` off) is never returned,
 * so its adapter is never called.
 */
export class AdapterRegistry {
  private readonly byPlatform = new Map<string, PlatformAdapter>()

  constructor(
    adapters: PlatformAdapter[],
    private readonly flags: FlagProvider
  ) {
    for (const adapter of adapters) {
      platformFlagName(adapter.platform)
      if (this.byPlatform.has(adapter.platform)) {
        throw new Error(`duplicate platform adapter: ${adapter.platform}`)
      }
      this.byPlatform.set(adapter.platform, adapter)
    }
  }

  status(): PlatformStatus[] {
    return [...this.byPlatform.values()].map((adapter) => ({
      platform: adapter.platform,
      enabled: this.flags.isPlatformEnabled(adapter.platform),
      transport: adapter.transport,
    }))
  }

  require(platform: string): PlatformAdapter {
    const adapter = this.byPlatform.get(platform)
    if (adapter === undefined) {
      throw new WorkerError('unknown_platform', 404)
    }
    if (!this.flags.isPlatformEnabled(platform)) {
      throw new WorkerError('platform_disabled', 409)
    }
    return adapter
  }
}

/** Builds the registry. The constructor throws if two adapters share a platform id. */
export function createAdapterRegistry(
  adapters: PlatformAdapter[],
  flags: FlagProvider
): AdapterRegistry {
  return new AdapterRegistry(adapters, flags)
}
