/**
 * @apex/money
 *
 * Monetary arithmetic with integer minor units.
 * NEVER use floats for money calculations.
 *
 * All amounts are stored as integers in minor units (cents/fen).
 * Rounding is always half away from zero to the minor unit (ADR-301).
 */

export { Money, MoneyError, type MoneyErrorCode, type MoneyInput } from './money.js'
export { convert, FxError, type FxConfig, type FxErrorCode } from './fx.js'
export { CURRENCY_MINOR_UNITS, FX_PIVOT_CURRENCY } from '@apex/shared-types/currency'
export type { ConvertedMoney, Currency, FxRate } from '@apex/shared-types/contracts'
