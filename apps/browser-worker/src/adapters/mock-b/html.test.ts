import { describe, expect, it } from 'vitest'

import { WorkerError } from '../../errors.js'

import { parseHtml, parsePriceText, priceOf, requireByTestId, type Price } from './html.js'

function priceElement(markup: string) {
  return requireByTestId(parseHtml(markup), 'price')
}

describe('parsePriceText', () => {
  const formats: Array<[string, Price]> = [
    ['£51.77', { minor: 5177, currency: 'GBP' }],
    ['$12.99', { minor: 1299, currency: 'USD' }],
    ['€1.234,56', { minor: 123456, currency: 'EUR' }],
    ['CNY 28.64', { minor: 2864, currency: 'CNY' }],
    ['US$ 4.32', { minor: 432, currency: 'USD' }],
    ['1,299.00 EUR', { minor: 129900, currency: 'EUR' }],
  ]

  for (const [raw, expected] of formats) {
    it(`parses ${raw}`, () => {
      expect(parsePriceText(raw)).toEqual(expected)
    })
  }

  it('parses thousands separators in both conventions', () => {
    expect(parsePriceText('£1,299.00')).toEqual({ minor: 129900, currency: 'GBP' })
    expect(parsePriceText('€1.299,00')).toEqual({ minor: 129900, currency: 'EUR' })
    expect(parsePriceText('$1,234,567.89')).toEqual({ minor: 123456789, currency: 'USD' })
    expect(parsePriceText('1.234.567,89 EUR')).toEqual({ minor: 123456789, currency: 'EUR' })
  })

  it('parses a decimal comma', () => {
    expect(parsePriceText('12,99 €')).toEqual({ minor: 1299, currency: 'EUR' })
    expect(parsePriceText('€ 12,99')).toEqual({ minor: 1299, currency: 'EUR' })
  })

  it('reads the amount from the surrounding visible text', () => {
    expect(parsePriceText('Price: £51.77 excl. VAT')).toEqual({
      minor: 5177,
      currency: 'GBP',
    })
    expect(parsePriceText('£\u00a051.77')).toEqual({ minor: 5177, currency: 'GBP' })
    expect(parsePriceText('CNY28.64')).toEqual({ minor: 2864, currency: 'CNY' })
  })

  const ambiguous = [
    '£51',
    '1,299',
    '£1,299',
    '£51.77 - £60.00',
    '£51.77 £51.77',
    '20% off £51.77',
    '£51.77 (20% VAT)',
    'JPY 100.00',
    '¥100.00',
    'A$12.99',
    '£51.77 USD',
    '12.99',
    '£51.77.00',
    '£1,29.00',
    '-£51.77',
    '£51.7',
    '£51.77 (100 pcs)',
    '',
    'free',
  ]

  for (const raw of ambiguous) {
    it(`rejects ${JSON.stringify(raw)}`, () => {
      expect(parsePriceText(raw)).toBeNull()
    })
  }
})

describe('priceOf', () => {
  it('prefers data-minor and data-currency over visible text', () => {
    const element = priceElement(
      '<span data-testid="price" data-minor="999" data-currency="GBP">$12.99</span>'
    )
    expect(priceOf(element, 'price')).toEqual({ minor: 999, currency: 'GBP' })
  })

  it('keeps a zero data-minor as a real price', () => {
    const element = priceElement(
      '<span data-testid="price" data-minor="0" data-currency="EUR">£51.77</span>'
    )
    expect(priceOf(element, 'price')).toEqual({ minor: 0, currency: 'EUR' })
  })

  it('falls back to visible text when data-minor is absent', () => {
    const element = priceElement('<span data-testid="price">£51.77</span>')
    expect(priceOf(element, 'price')).toEqual({ minor: 5177, currency: 'GBP' })
  })

  it('falls back to visible text when data-minor is not an integer', () => {
    const element = priceElement(
      '<span data-testid="price" data-minor="51.77" data-currency="GBP">$12.99</span>'
    )
    expect(priceOf(element, 'price')).toEqual({ minor: 1299, currency: 'USD' })
  })

  it('falls back to visible text when data-minor is not numeric', () => {
    const element = priceElement(
      '<span data-testid="price" data-minor="oops" data-currency="USD">€1.234,56</span>'
    )
    expect(priceOf(element, 'price')).toEqual({ minor: 123456, currency: 'EUR' })
  })

  it('reads visible text across nested elements', () => {
    const element = priceElement('<span data-testid="price">£<b>51.77</b></span>')
    expect(priceOf(element, 'price')).toEqual({ minor: 5177, currency: 'GBP' })
  })

  it('returns null when neither the attributes nor the text carry a price', () => {
    const element = priceElement('<span data-testid="price">Call us</span>')
    expect(priceOf(element, 'price')).toBeNull()
  })

  it('still refuses a valid data-minor without a currency', () => {
    const element = priceElement('<span data-testid="price" data-minor="999">$12.99</span>')
    expect(() => priceOf(element, 'price')).toThrow(WorkerError)
  })
})
