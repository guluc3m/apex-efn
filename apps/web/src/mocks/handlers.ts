import type {
  EffectiveConfig,
  Mission,
  MissionEvent,
  NegotiationMessageTranslation,
  OnboardingSession,
  Problem,
  SigningSession,
  SourcingRequest,
} from '@apex/shared-types/contracts'
import { http, HttpResponse } from 'msw'

/**
 * MSW handlers for screens built before the orchestrator answers.
 *
 * The contract has no response examples yet (DEV-2 adds them in a follow-up, guluc3m/apex-efn#83),
 * so the bodies below are typed with the generated contract types: a contract change that makes
 * one stale fails `pnpm typecheck`. `handlers.test.ts` also parses each one with the generated Zod
 * schema. Values are inert placeholders, never business defaults.
 *
 * Only routes that are still 501 in the orchestrator should stay mocked; the live ones can be
 * dropped from `activeHandlers` once the BFF is pointed at a running orchestrator.
 */

const NOW = '2026-11-09T09:00:00Z'

export const sourcingRequestFixture: SourcingRequest = {
  id: 'sr_mock_1',
  status: 'normalized',
  spec: { description: 'PET bottle 500 ml with flip-top cap' },
  quantity_tiers: [{ quantity: 5000, priority: 'primary' }],
  delivery_country: 'ES',
  needs_clarification: [],
  created_at: NOW,
}

export const missionFixture: Mission = {
  id: 'ms_mock_1',
  sourcing_request_id: sourcingRequestFixture.id,
  state: 'sourcing',
  offers_discovered: 0,
  offers_negotiated: 0,
  offers_in_gate: 0,
  tokens_used: 0,
  // The schema requires >= 1. Inert placeholder for a mock, not a budget the product proposes.
  token_budget: 1,
  started_at: NOW,
}

export const effectiveConfigFixture: EffectiveConfig = {
  tenant_id: 'tenant-a',
  category: null,
  config_version: 1,
  content_hash: `sha256:${'0'.repeat(64)}`,
  resolved_at: NOW,
  // Unset values stay unset: the UI must render "sin definir", never a made-up default.
  values: {},
}

export const onboardingSessionFixture: OnboardingSession = {
  id: 'ob_mock_1',
  status: 'profiling',
  // Placeholder identity for a mock only; the wizard collects the real one.
  company_profile: { legal_name: 'Mock Company S.L.', tax_id: 'MOCK0000', country: 'ES', base_currency: 'EUR' },
  effective_config: effectiveConfigFixture,
  steps: [
    { step: 'company', done: 4, warnings: 0, pending: 0 },
    { step: 'sector', done: 1, warnings: 0, pending: 2 },
    { step: 'finance', done: 0, warnings: 0, pending: 1 },
  ],
  created_at: NOW,
  updated_at: NOW,
}

export const missionEventFixture: MissionEvent = {
  id: '1',
  mission_id: missionFixture.id,
  type: 'state_changed',
  at: NOW,
  data: { state: missionFixture.state },
}

export const reauthProblemFixture: Problem & { error: 'reauth_required'; reason: 'session_expired' } = {
  type: 'about:blank',
  title: 'Reauthentication required',
  status: 428,
  error: 'reauth_required',
  reason: 'session_expired',
}

// Inert fixture window (the real length comes from the server's expires_at, never from the UI).
export const signingSessionFixture: SigningSession = {
  id: 'ss_mock_1',
  user_id: 'user_mock_1',
  key_id: 'key_mock_1',
  auth_method: 'keycloak_step_up',
  auth_at: NOW,
  expires_at: '2026-11-09T09:15:00Z',
  device_fingerprint_ref: 'device_mock_1',
  decisions_signed: [],
  max_decisions: 5,
  remaining_decisions: 5,
  status: 'active',
  server_time: NOW,
}

export const translationFixture: NegotiationMessageTranslation = {
  message_id: 'neg_mock_1:1',
  target_language: 'es',
  text: 'Texto traducido (simulado).',
}

const API = '*/api/v1'

export const handlers = [
  http.post(`${API}/onboarding/sessions`, () => HttpResponse.json(onboardingSessionFixture, { status: 201 })),
  http.get(`${API}/categories`, () => HttpResponse.json({ items: [{ id: 'bearings' }, { id: 'valves' }] })),
  http.get(`${API}/onboarding/sessions`, () => HttpResponse.json({ items: [onboardingSessionFixture] })),
  http.get(`${API}/onboarding/sessions/:id`, ({ params }) =>
    HttpResponse.json({ ...onboardingSessionFixture, id: String(params.id) }),
  ),
  http.post(`${API}/sourcing-requests`, () => HttpResponse.json(sourcingRequestFixture, { status: 201 })),
  http.post(`${API}/missions`, () => HttpResponse.json(missionFixture, { status: 201 })),
  http.get(`${API}/missions/:id`, ({ params }) =>
    HttpResponse.json({ ...missionFixture, id: String(params.id) }),
  ),
  http.get(`${API}/missions/:id/events`, ({ params }) => {
    const body = `id: 1\nevent: state_changed\ndata: ${JSON.stringify({ ...missionEventFixture, mission_id: params.id })}\n\n`
    return new HttpResponse(body, { headers: { 'content-type': 'text/event-stream' } })
  }),
  http.post(`${API}/signing-sessions`, () => HttpResponse.json(signingSessionFixture, { status: 201 })),
  http.get(`${API}/signing-sessions/:id`, ({ params }) =>
    HttpResponse.json({ ...signingSessionFixture, id: String(params.id) }),
  ),
  http.delete(`${API}/signing-sessions/:id`, ({ params }) =>
    HttpResponse.json({ ...signingSessionFixture, id: String(params.id), status: 'closed' }),
  ),
  http.post(`${API}/negotiations/:id/messages/:messageId/translate`, async ({ params, request }) => {
    const { target_language } = (await request.json()) as { target_language: NegotiationMessageTranslation['target_language'] }
    return HttpResponse.json({ ...translationFixture, message_id: String(params.messageId), target_language })
  }),
  http.get(`${API}/config/effective`, () => HttpResponse.json(effectiveConfigFixture)),
]
