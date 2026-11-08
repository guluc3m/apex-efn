/**
 * @apex/money
 *
 * Monetary arithmetic with integer minor units.
 * NEVER use floats for money calculations.
 *
 * All amounts are stored as integers in minor units (cents/fen).
 * Rounding is always half-up to the minor unit.
 */

export { Money, type MoneyInput } from './money.js'
export { FxConverter, type FxRateProvider } from './fx.js'
export { CURRENCY_MINOR_UNITS, FX_PIVOT_CURRENCY } from '@apex/shared-types/currency'
export type { Currency, FxRate } from '@apex/shared-types/currency'
