import { describe, expect, it } from 'vitest'

import { formatMinor, parseLastPrice } from './money.js'

describe('money helpers', () => {
  it('formats minor units', () => {
    expect(formatMinor(445)).toBe('4.45')
    expect(formatMinor(5)).toBe('0.05')
    expect(formatMinor(123400)).toBe('1234.00')
  })

  it('parses the last price with a code or symbol and ignores bare quantities', () => {
    expect(parseLastPrice('5000 units at EUR 4.10 please')).toEqual({ minor: 410, currency: 'EUR' })
    expect(parseLastPrice('could you do 3,95€?')).toEqual({ minor: 395, currency: 'EUR' })
    expect(parseLastPrice('¥33 or 32.5 CNY')).toEqual({ minor: 3250, currency: 'CNY' })
    expect(parseLastPrice('$4')).toEqual({ minor: 400, currency: 'USD' })
    expect(parseLastPrice('5000 units')).toBeNull()
    expect(parseLastPrice('£3.20')).toEqual({ minor: 320, currency: 'GBP' })
  })
})
