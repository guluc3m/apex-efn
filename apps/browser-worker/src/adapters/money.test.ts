import { describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'

import { parseDecimalMinor, toContractCurrency } from './money.js'

describe('parseDecimalMinor', () => {
  it.each([
    ['4.45', 445],
    ['4,45', 445],
    ['12', 1200],
    ['0.5', 50],
    ['0.05', 5],
    ['0.10', 10],
    ['4.3', 430],
    ['4.35', 435],
    ['1234567.89', 123456789],
    ['1 234.50', 123450],
    ['1,234.50', 123450],
    ['1.234,50', 123450],
    ['1 234,5', 123450],
    ['1,234,567', 123456700],
    ['1.234.567', 123456700],
    ['1 234', 123400],
    ['1,5', 150],
    ['1.5', 150],
    ['  12.50  ', 1250],
    ['9007199254740.99', 900719925474099],
    ['90071992547409.91', Number.MAX_SAFE_INTEGER],
  ])('parses %j as %i minor units', (value, minor) => {
    expect(parseDecimalMinor(value)).toBe(minor)
  })

  it('parses the float-trap pair exactly', () => {
    expect(parseDecimalMinor('0.1') + parseDecimalMinor('0.2')).toBe(30)
    expect(parseDecimalMinor('4.35') * 2).toBe(870)
  })

  it.each([
    '1.005',
    '1,234',
    '1.234',
    '4.450',
    '4,4500',
    '1.2345',
    '-4.50',
    '+5',
    '',
    '   ',
    'abc',
    '12.5.0',
    '1,234,56',
    '1234,56,78',
    '1e3',
    '$12',
    '12 €',
    '.5',
    '12,',
    '12.',
    '1.234.5',
    '90071992547409.92',
    '99999999999999999999',
  ])('rejects %j', (value) => {
    expect(() => parseDecimalMinor(value)).toThrow(WorkerError)
  })

  it('reports a rejected price as dom_changed without echoing the value', () => {
    let caught: unknown
    try {
      parseDecimalMinor('1.005')
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(WorkerError)
    expect(caught).toMatchObject({ code: 'dom_changed', status: 502, retryable: false })
    expect((caught as WorkerError).detail).not.toContain('1.005')
  })
})

describe('toContractCurrency', () => {
  it.each([
    ['EUR', 'EUR'],
    ['eur', 'EUR'],
    [' usd ', 'USD'],
    ['CNY', 'CNY'],
    ['cny', 'CNY'],
    ['RMB', 'CNY'],
    ['rmb', 'CNY'],
  ])('maps %j to %s', (code, currency) => {
    expect(toContractCurrency(code)).toBe(currency)
  })

  it.each(['JPY', 'GBP', '', 'EURO', '€'])('returns null for %j', (code) => {
    expect(toContractCurrency(code)).toBeNull()
  })
})
