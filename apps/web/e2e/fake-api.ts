import { createHash } from 'node:crypto'

import type {
  ApprovalView,
  Deal,
  Decision,
  FinancialImport,
  GateQueueItem,
  Mission,
  Negotiation,
  NegotiationMessage,
  Offer,
  SigningKey,
  SigningSession,
} from '@apex/shared-types/contracts'
import type { Page, Route } from '@playwright/test'

/**
 * Test-layer stand-in for the orchestrator, answered with `page.route` (the BFF path the browser calls).
 * It is stateful just enough for a flow: keys, the signing window, decisions, gate items, a negotiation.
 * It never decides business values: every band, score and verdict below is a fixture the UI only displays.
 * Pages using it must run with `serviceWorkers: 'block'` so MSW does not answer first.
 */

/** The page clock and the server clock agree on this instant, so countdowns are deterministic. */
export const NOW = '2026-11-09T09:00:00.000Z'
const money = (amount_minor: number) => ({ amount_minor, currency: 'EUR' as const })

const offer = (id: string, over: Partial<Offer> = {}): Offer => ({
  id,
  mission_id: 'ms_1',
  platform: 'mock-a',
  platform_offer_id: `p-${id}`,
  product_key: 'pet-500',
  title: `PET bottle 500 ml (${id})`,
  seller_id: `sel_${id}`,
  seller_name: `Seller ${id}`,
  unit_price: { ...money(1200), converted: false, fx_provisional: false },
  moq: 1000,
  state: 'sanity_checked',
  discovered_at: NOW,
  seller_confidence: {
    seller_id: `sel_${id}`,
    score: 82,
    band: 'high',
    signals_normalized: { tenure: 0.9 },
    penalties: [],
    flags: [],
    model_version: 'trust-v1',
    computed_at: NOW,
  },
  price_sanity_check: {
    offer_id: id,
    reference_price_eur: money(1250),
    median: money(1250),
    dispersion_measure: 'mad',
    dispersion_value: 40,
    sample_size: 12,
    relative_deviation: -0.04,
    band: 'normal',
    decision: 'negotiate',
    explanations: [],
    config_version: '1',
    checked_at: NOW,
  },
  financial_fit: {
    offer_id: id,
    landed_cost: {
      unit_price: money(1200),
      quantity: 5000,
      lines: [{ code: 'goods', amount: money(6_000_000) }],
      total: money(6_000_000),
      unit_landed_cost: money(1200),
    },
    verdict: 'within_budget',
    reasons: [],
    financials_stale: false,
    computed_at: NOW,
  },
  ...over,
})

const allActions = (blocked: Partial<Record<string, { code: string; message: string }>> = {}) =>
  (['follow', 'renegotiate', 'takeover', 'hold', 'discard'] as const).map((action) => ({
    action,
    allowed: !blocked[action],
    blocked_by: blocked[action] ? [blocked[action]] : [],
  })) as Deal['actions']

const deal = (id: string, o: Offer, over: Partial<Deal> = {}): Deal => ({
  id,
  mission_id: 'ms_1',
  offer: o,
  state: 'open',
  price_band: o.price_sanity_check?.band ?? 'normal',
  confidence_band: o.seller_confidence?.band ?? 'high',
  financial_verdict: 'within_budget',
  signature_status: 'unsigned',
  actions: allActions(),
  updated_at: NOW,
  ...over,
})

export const ANOMALOUS = offer('anom', {
  unit_price: { ...money(120), converted: false, fx_provisional: false },
  price_sanity_check: {
    ...offer('x').price_sanity_check!,
    offer_id: 'anom',
    band: 'atypical',
    decision: 'human_gate',
    relative_deviation: -0.9,
    explanations: [],
  },
})
export const LOW_TRUST = offer('low', {
  platform: 'mock-b',
  seller_confidence: {
    ...offer('x').seller_confidence!,
    seller_id: 'sel_low',
    score: 31,
    band: 'low',
  },
})
export const NORMAL = offer('ok')

export const blockedFollow = (code: string, message: string) =>
  allActions({ follow: { code, message } })

export const BLOCK_PRICE =
  'Price is atypical: an unblock decision is required before it can be followed.'
export const BLOCK_SELLER =
  'Seller confidence is low: an unblock decision is required before it can be followed.'

export function dashboardFixtures() {
  const deals: Deal[] = [
    deal('d_anom', ANOMALOUS, {
      actions: blockedFollow('price_band_requires_unblock', BLOCK_PRICE),
    }),
    deal('d_low', LOW_TRUST, {
      actions: blockedFollow('seller_band_requires_unblock', BLOCK_SELLER),
    }),
    deal('d_ok', NORMAL, { recommendation_rank: 1 }),
  ]
  const gate: GateQueueItem[] = [
    {
      id: 'g_anom',
      mission_id: 'ms_1',
      offer_id: 'anom',
      causes: ['price_atypical'],
      created_at: NOW,
      sla_due_at: '2026-11-09T17:00:00.000Z',
      status: 'open',
      resolution: null,
      decision_id: null,
    },
    {
      id: 'g_low',
      mission_id: 'ms_1',
      offer_id: 'low',
      causes: ['seller_low'],
      created_at: NOW,
      sla_due_at: '2026-11-09T18:00:00.000Z',
      status: 'open',
      resolution: null,
      decision_id: null,
    },
  ]
  return { deals, gate }
}

export interface Backend {
  keys: SigningKey[]
  session: SigningSession | null
  decisions: Map<string, Decision>
  signed: { id: string; body: Record<string, unknown> }[]
  actions: { path: string; body: Record<string, unknown> }[]
  deals: Deal[]
  gate: GateQueueItem[]
  approvals: ApprovalView[]
  negotiation: Negotiation | null
  messages: NegotiationMessage[]
  financialImport: FinancialImport | null
  unhandled: string[]
  /** Requests answered per `METHOD path`, for assertions. */
  calls: string[]
}

export const newBackend = (over: Partial<Backend> = {}): Backend => ({
  keys: [],
  session: null,
  decisions: new Map(),
  signed: [],
  actions: [],
  deals: [],
  gate: [],
  approvals: [],
  negotiation: null,
  messages: [],
  financialImport: null,
  unhandled: [],
  calls: [],
  ...over,
})

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })
const problem = (
  route: Route,
  status: number,
  title: string,
  extra: Record<string, unknown> = {}
) =>
  route.fulfill({
    status,
    contentType: 'application/problem+json',
    body: JSON.stringify({ type: 'about:blank', title, status, ...extra }),
  })

/** Builds a pending decision whose hash really is the SHA-256 of its canonical payload, so the UI's check passes honestly. */
export function pendingDecision(
  id: string,
  type: Decision['type'],
  subject: string,
  required = 1
): Decision {
  // Keys are already in RFC 8785 order and ASCII, so JSON.stringify is the canonical form here.
  const canonical = JSON.stringify({ subject, type })
  return {
    id,
    type,
    subject_ref: subject,
    status: 'pending_signature',
    payload_canonical: canonical,
    payload_hash: createHash('sha256').update(canonical).digest('hex'),
    requires_immediate_reauth: false,
    required_signers: required,
    signatures: [],
    created_at: NOW,
  }
}

export function sessionAt(over: Partial<SigningSession> = {}): SigningSession {
  return {
    id: 'ss_1',
    user_id: 'user-e2e',
    key_id: 'key_1',
    auth_method: 'keycloak_step_up',
    auth_at: NOW,
    expires_at: '2026-11-09T09:15:00.000Z',
    device_fingerprint_ref: 'dev',
    decisions_signed: [],
    max_decisions: 3,
    remaining_decisions: 3,
    status: 'active',
    server_time: NOW,
    ...over,
  }
}

/** Keycloak is not in the suite: the step-up entry answers 204 so the page stays put and the window opens right after. */
export const stubStepUp = (page: Page) =>
  page.route('**/api/auth/signin**', (r) => r.fulfill({ status: 204 }))

export async function installApi(page: Page, b: Backend): Promise<void> {
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^.*\/api\/v1/, '')
    const m = req.method()
    const body = (
      req.headers()['content-type']?.includes('json') ? req.postDataJSON() : {}
    ) as Record<string, unknown>
    b.calls.push(`${m} ${path}`)
    const q = (k: string) => url.searchParams.get(k)
    let g: RegExpMatchArray | null

    if (m === 'GET' && path === '/keys/me') return json(route, { items: b.keys })
    if (m === 'POST' && path === '/keys/me') {
      const key: SigningKey = {
        id: `key_${b.keys.length + 1}`,
        owner_id: 'user-e2e',
        owner_type: 'human',
        public_key: String(body.public_key),
        alg: 'Ed25519',
        created_at: NOW,
      }
      b.keys.push(key)
      return json(route, key, 201)
    }
    if (m === 'POST' && path === '/signing-sessions') {
      b.session = sessionAt({ key_id: String(body.key_id) })
      return json(route, b.session, 201)
    }
    if ((g = path.match(/^\/signing-sessions\/([^/]+)$/)) && m === 'GET')
      return json(route, b.session)
    if ((g = path.match(/^\/decisions\/([^/]+)$/)) && m === 'GET') {
      const d = b.decisions.get(g[1]!)
      return d ? json(route, d) : problem(route, 404, 'Not found')
    }
    if ((g = path.match(/^\/decisions\/([^/]+)\/sign$/)) && m === 'POST') {
      const d = b.decisions.get(g[1]!)
      if (!d || !b.session)
        return problem(route, 428, 'Reauth', {
          error: 'reauth_required',
          reason: 'session_expired',
        })
      b.signed.push({ id: d.id, body })
      b.session = {
        ...b.session,
        decisions_signed: [...b.session.decisions_signed, d.id],
        remaining_decisions: b.session.remaining_decisions - 1,
      }
      const sig = {
        decision_id: d.id,
        signer_type: 'human' as const,
        signer_id: 'user-e2e',
        key_id: String(body.key_id),
        alg: 'Ed25519' as const,
        payload_hash: String(body.payload_hash),
        signature: String(body.signature),
        signed_at: NOW,
        signing_session_id: b.session.id,
        chain_hash: 'chain-e2e',
      }
      const done: Decision = {
        ...d,
        signatures: [...d.signatures, sig],
        status: d.signatures.length + 1 >= d.required_signers ? 'signed' : 'pending_signature',
      }
      b.decisions.set(d.id, done)
      return json(route, done)
    }

    if (m === 'GET' && path === '/dashboard/deals') {
      const f = ['price_band', 'confidence_band', 'financial_verdict', 'signature_status'] as const
      const items = b.deals.filter(
        (d) =>
          f.every((k) => !q(k) || d[k] === q(k)) &&
          (!q('platform') || d.offer.platform === q('platform'))
      )
      return json(route, { items, next_cursor: null })
    }
    if ((g = path.match(/^\/dashboard\/deals\/([^/]+)\/actions$/)) && m === 'POST') {
      b.actions.push({ path, body })
      const id = `dec_${b.decisions.size + 1}`
      b.decisions.set(id, pendingDecision(id, body.action as Decision['type'], g[1]!))
      return json(route, { decision_id: id, status: 'pending_signature' }, 202)
    }
    if (m === 'GET' && path === '/gate/queue') {
      return json(route, {
        items: b.gate.filter(
          (i) =>
            i.status === (q('status') ?? i.status) &&
            (!q('type') || i.causes.includes(q('type') as never))
        ),
        next_cursor: null,
      })
    }
    if ((g = path.match(/^\/gate\/queue\/([^/]+)\/actions$/)) && m === 'POST') {
      b.actions.push({ path, body })
      const id = `dec_${b.decisions.size + 1}`
      b.decisions.set(id, pendingDecision(id, 'gate_override_discard', g[1]!))
      return json(route, { decision_id: id, status: 'pending_signature' }, 202)
    }
    if ((g = path.match(/^\/missions\/([^/]+)$/)) && m === 'GET') {
      const mission: Mission = {
        id: g[1]!,
        sourcing_request_id: 'sr_1',
        state: 'awaiting_decision',
        offers_discovered: 3,
        offers_negotiated: 1,
        offers_in_gate: 2,
        tokens_used: 0,
        token_budget: 1,
        started_at: NOW,
      }
      return json(route, mission)
    }
    if ((g = path.match(/^\/missions\/([^/]+)\/offers$/)) && m === 'GET')
      return json(route, { items: b.deals.map((d) => d.offer), next_cursor: null })
    if (path.endsWith('/recommendation') || path === '/profiles')
      return problem(route, 404, 'Not found')
    if (m === 'GET' && path === '/approvals')
      return json(route, { items: b.approvals, next_cursor: null })
    if ((g = path.match(/^\/approvals\/([^/]+)$/)) && m === 'GET') {
      const a = b.approvals.find((x) => x.id === g![1])
      return a ? json(route, a) : problem(route, 404, 'Not found')
    }

    if ((g = path.match(/^\/negotiations\/([^/]+)$/)) && m === 'GET')
      return b.negotiation ? json(route, b.negotiation) : problem(route, 404, 'Not found')
    if (/^\/negotiations\/[^/]+\/messages$/.test(path) && m === 'GET')
      return json(route, { items: b.messages, next_cursor: null })
    if (
      /^\/negotiations\/[^/]+\/approve$/.test(path) &&
      m === 'POST' &&
      b.negotiation?.pending_draft
    ) {
      const draft = b.negotiation.pending_draft
      b.messages.push({
        id: `m${b.messages.length + 1}`,
        negotiation_id: b.negotiation.id,
        role: 'agent',
        content: draft.text,
        at: NOW,
        approved_by: 'user-e2e',
      })
      b.negotiation = { ...b.negotiation, state: 'running', pending_draft: null }
      return json(route, b.negotiation)
    }

    if (/^\/onboarding\/[^/]+\/financial-csv\/mapping$/.test(path))
      return json(route, { mappings: [], canonical_columns: [] })
    if (/^\/onboarding\/[^/]+\/financial-csv$/.test(path) && m === 'POST')
      return json(route, b.financialImport, 201)
    if (/^\/onboarding\/[^/]+\/financial-csv\/activate$/.test(path) && m === 'POST') {
      b.actions.push({ path, body })
      b.decisions.set(
        'dec_act',
        pendingDecision('dec_act', 'financial_snapshot_activation', String(body.import_id))
      )
      return json(route, { decision_id: 'dec_act', status: 'pending_signature' }, 202)
    }
    if (m === 'POST' && path === '/onboarding/sessions')
      return json(
        route,
        {
          id: 'ob_1',
          status: 'profiling',
          company_profile: {},
          steps: [],
          created_at: NOW,
          updated_at: NOW,
        },
        201
      )

    b.unhandled.push(`${m} ${path}`)
    return problem(route, 404, 'Not found')
  })
}
