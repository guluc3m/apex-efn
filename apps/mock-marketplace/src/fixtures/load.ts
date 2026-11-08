import { readFileSync } from 'node:fs'

import { ProductsFileSchema, SellersFileSchema, type Catalog } from './schema.js'

const FIXTURES_DIR = new URL('../../fixtures/', import.meta.url)

function readJson(name: string): unknown {
  return JSON.parse(readFileSync(new URL(name, FIXTURES_DIR), 'utf8')) as unknown
}

/** Cross-file checks that zod cannot express: unique ids, seller references, consistent tiers. */
export function validateCatalog(catalog: Catalog): Catalog {
  const errors: string[] = []
  const sellers = new Map<string, Catalog['sellers'][number]>()
  const reviewIds = new Set<string>()
  for (const s of catalog.sellers) {
    if (sellers.has(s.id)) errors.push(`duplicate seller id ${s.id}`)
    sellers.set(s.id, s)
    for (const r of s.reviews) {
      if (reviewIds.has(r.id)) errors.push(`duplicate review id ${r.id}`)
      reviewIds.add(r.id)
    }
  }
  const productIds = new Set<string>()
  for (const p of catalog.products) {
    if (productIds.has(p.id)) errors.push(`duplicate product id ${p.id}`)
    productIds.add(p.id)
    const seller = sellers.get(p.sellerId)
    if (!seller) errors.push(`product ${p.id}: unknown seller ${p.sellerId}`)
    else if (seller.platform !== p.platform)
      errors.push(`product ${p.id}: seller on another platform`)
    const first = p.priceTiers[0]
    if (first && (first.minQuantity !== p.moq || first.unitPriceMinor !== p.unitPriceMinor)) {
      errors.push(`product ${p.id}: first tier must start at moq with the list price`)
    }
    const last = p.priceTiers.at(-1)
    if (last && last.maxQuantity !== null)
      errors.push(`product ${p.id}: last tier must be open-ended`)
  }
  if (errors.length > 0)
    throw new Error(`Invalid mock-marketplace fixtures:\n- ${errors.join('\n- ')}`)
  return catalog
}

export function loadCatalog(): Catalog {
  const { sellers } = SellersFileSchema.parse(readJson('sellers.json'))
  const { products } = ProductsFileSchema.parse(readJson('products.json'))
  return validateCatalog({ sellers, products })
}
