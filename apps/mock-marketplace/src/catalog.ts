import type { Catalog, PlatformId, Product, Seller } from './fixtures/schema.js'

function tokens(value: string): string[] {
  return value
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 0)
}

/** Every query token must appear in the title, product key or description. Stable fixture order. */
export function search(catalog: Catalog, platform: PlatformId, query: string): Product[] {
  const q = tokens(query)
  return catalog.products.filter((p) => {
    if (p.platform !== platform) return false
    if (q.length === 0) return true
    const hay = new Set(tokens(`${p.title} ${p.productKey} ${p.description}`))
    return q.every((t) => hay.has(t))
  })
}

export function findProduct(
  catalog: Catalog,
  platform: PlatformId,
  id: string
): Product | undefined {
  return catalog.products.find((p) => p.platform === platform && p.id === id)
}

export function findSeller(catalog: Catalog, platform: PlatformId, id: string): Seller | undefined {
  return catalog.sellers.find((s) => s.platform === platform && s.id === id)
}

export function sellerProducts(catalog: Catalog, sellerId: string): Product[] {
  return catalog.products.filter((p) => p.sellerId === sellerId)
}
