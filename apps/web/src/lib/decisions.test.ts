import { describe, expect, it } from 'vitest'

import { blockedCodes, dealActionBody, emptyActionForm, remaining } from './decisions'

describe('dealActionBody', () => {
  it('requires reason code and comment to discard', () => {
    expect(dealActionBody('discard', emptyActionForm)).toBeNull()
    expect(dealActionBody('discard', { ...emptyActionForm, discardReason: 'duplicate' })).toBeNull()
    expect(dealActionBody('discard', { ...emptyActionForm, discardReason: 'duplicate', comment: ' dup ' })).toEqual({
      action: 'discard',
      discard_reason: 'duplicate',
      comment: 'dup',
    })
  })
  it('builds the other actions', () => {
    expect(dealActionBody('follow', emptyActionForm)).toEqual({ action: 'follow' })
    expect(dealActionBody('hold', { ...emptyActionForm, holdUntil: '2026-12-01' })).toEqual({ action: 'hold', hold_until: '2026-12-01' })
    expect(dealActionBody('renegotiate', emptyActionForm)).toEqual({ action: 'renegotiate', instructions: null })
  })
})

describe('blockedCodes', () => {
  it('is null when allowed and lists the API codes otherwise', () => {
    expect(blockedCodes({ action: 'follow', allowed: true, blocked_by: [] })).toBeNull()
    expect(blockedCodes({ action: 'follow', allowed: false, blocked_by: [{ code: 'financials_stale', message: 'x' }] })).toEqual(['financials_stale'])
    expect(blockedCodes({ action: 'follow', allowed: false, blocked_by: [] })).toEqual(['unknown'])
  })
})

describe('remaining', () => {
  it('formats and flags overdue', () => {
    const now = Date.parse('2026-11-10T10:00:00Z')
    expect(remaining('2026-11-10T12:05:00Z', now)).toEqual({ label: '2:05', overdue: false })
    expect(remaining('2026-11-10T09:30:00Z', now)).toEqual({ label: '0:30', overdue: true })
  })
})
