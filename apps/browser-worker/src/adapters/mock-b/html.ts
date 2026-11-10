/**
 * Tiny helpers over `node-html-parser` for the `mock-b` adapter.
 *
 * Every read that can fail names the `data-testid` it wanted and nothing else: a page that changed shape answers
 * `dom_changed` (the runbook in docs/runbooks/dom-change.md) without echoing page content, which may contain a
 * seller's data or a price.
 */

import { parse, type HTMLElement } from 'node-html-parser'

import { WorkerError } from '../../errors.js'

export type Html = HTMLElement

export function parseHtml(body: string): Html {
  return parse(body)
}

export function domChanged(what: string): WorkerError {
  return new WorkerError('dom_changed', 502, { detail: `mock-b page changed: missing ${what}` })
}

export function byTestId(root: Html, testId: string): Html | null {
  return root.querySelector(`[data-testid="${testId}"]`)
}

export function allByTestId(root: Html, testId: string): Html[] {
  return root.querySelectorAll(`[data-testid="${testId}"]`)
}

export function requireByTestId(root: Html, testId: string): Html {
  const element = byTestId(root, testId)
  if (element === null) {
    throw domChanged(testId)
  }
  return element
}

export function attr(element: Html, name: string): string | null {
  const value = element.getAttribute(name)
  return value === undefined ? null : value
}

export function requireAttr(element: Html, name: string, testId: string): string {
  const value = attr(element, name)
  if (value === null || value === '') {
    throw domChanged(`${name} on ${testId}`)
  }
  return value
}

export function text(element: Html): string {
  return element.textContent.trim()
}

/** Integer `data-*` attribute. A missing or non-numeric value is a page change, never a zero. */
export function intAttr(element: Html, name: string, testId: string): number {
  const raw = requireAttr(element, name, testId)
  const value = Number(raw)
  if (!Number.isInteger(value)) {
    throw domChanged(`numeric ${name} on ${testId}`)
  }
  return value
}

export function optionalIntAttr(element: Html, name: string): number | null {
  const raw = attr(element, name)
  if (raw === null || raw === '') {
    return null
  }
  const value = Number(raw)
  return Number.isInteger(value) ? value : null
}

/** `data-minor` + `data-currency` on a price element. */
export function priceOf(element: Html, testId: string): { minor: number; currency: string } {
  return {
    minor: intAttr(element, 'data-minor', testId),
    currency: requireAttr(element, 'data-currency', testId),
  }
}

/** "30%" -> 0.3. Anything else is a page change. */
export function ratioOf(element: Html, testId: string): number | null {
  const raw = attr(element, 'data-value')
  if (raw === null || raw === '') {
    return null
  }
  const match = /^(\d+(?:\.\d+)?)%$/.exec(raw)
  if (match?.[1] === undefined) {
    throw domChanged(`percentage on ${testId}`)
  }
  return Number(match[1]) / 100
}

/** "yes" | "no" -> boolean; anything else is `null` (the platform did not say). */
export function booleanOf(element: Html): boolean | null {
  const raw = attr(element, 'data-value')
  if (raw === 'yes') {
    return true
  }
  if (raw === 'no') {
    return false
  }
  return null
}

export function numberValue(element: Html): number | null {
  const raw = attr(element, 'data-value')
  if (raw === null || raw === '') {
    return null
  }
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}
