/**
 * Platform Adapters
 *
 * Each adapter implements the PlatformAdapter interface for a specific platform.
 * Adding a new platform = new adapter + fixtures + tests + compliance doc.
 */

import type { RawSellerSignals } from '@apex/shared-types/seller'

/**
 * Transport type for the adapter
 */
export type TransportType = 'http' | 'browser'

/**
 * Search result from a platform
 */
export interface SearchResult {
  platformOfferId: string
  productUrl: string
  title: string
  unitPriceMinor: number
  currency: string
  moq: number
  sellerId: string
  sellerName: string
}

/**
 * Product details
 */
export interface ProductDetails {
  description: string
  specifications: Record<string, string>
  certifications: string[]
  imageUrls: string[]
  priceTiers: Array<{
    minQuantity: number
    maxQuantity: number | null
    unitPriceMinor: number
    currency: string
  }>
  shipping: {
    costMinor: number
    currency: string
    minDays: number
    maxDays: number
  } | null
  leadTimeDays: number | null
}

/**
 * Platform adapter interface
 */
export interface PlatformAdapter {
  readonly platform: string
  readonly transport: TransportType

  /**
   * Search for products matching the query
   */
  search(query: string, filters?: Record<string, unknown>): Promise<SearchResult[]>

  /**
   * Get detailed product information
   */
  getProduct(productUrl: string): Promise<ProductDetails>

  /**
   * Get seller information
   */
  getSeller(sellerId: string): Promise<{ name: string; country: string | null }>

  /**
   * Get raw seller signals for confidence scoring
   */
  getSellerSignals(sellerId: string): Promise<RawSellerSignals>

  /**
   * Open chat with seller (browser transport only)
   */
  openChat?(sellerId: string, productUrl: string): Promise<string>

  /**
   * Send message in chat (browser transport only)
   */
  sendMessage?(chatId: string, message: string): Promise<void>

  /**
   * Read messages from chat (browser transport only)
   */
  readMessages?(chatId: string, since?: string): Promise<Array<{ role: string; content: string; timestamp: string }>>
}
