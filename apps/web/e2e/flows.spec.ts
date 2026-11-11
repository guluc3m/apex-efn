import { expect, test, type Page } from '@playwright/test'

import {
  dashboardFixtures,
  installApi,
  newBackend,
  pendingDecision,
  stubStepUp,
  NOW,
  BLOCK_PRICE,
  BLOCK_SELLER,
  type Backend,
} from './fake-api'
import { signInAs } from './session'

// D6-08. Flows from spec 5.11. Those that run here are driven through the real UI; the API is
// answered by MSW (default) or by explicit network stubs where a specific status is the point.
// The signed flows use the in-test API of fake-api.ts; nothing is faked in app code.
test.skip(!process.env.E2E_BROWSER && !process.env.GITHUB_ACTIONS, 'set E2E_BROWSER=1 to run')

test.beforeEach(async ({ context }) => signInAs(context))

async function requestMission(page: Page) {
  await page.goto('/es/misiones/nueva')
  await page.getByLabel('País de entrega').fill('ES')
  await page
    .getByPlaceholder('Describe lo que necesitas')
    .fill('Botellas PET de 500 ml con tapón flip-top')
  await page.getByRole('button', { name: 'Enviar' }).click()
}

test('mission: natural-language request, review and launch lands on the mission', async ({
  page,
}) => {
  await requestMission(page)
  await expect(page.getByLabel('Producto')).toHaveValue('PET bottle 500 ml with flip-top cap')
  await page.getByRole('button', { name: 'Lanzar misión' }).click()
  await expect(page).toHaveURL(/\/es\/misiones\/ms_mock_1$/)
})

// Network stubs need the page's own requests, so MSW's service worker is blocked here.
test.describe('API statuses', () => {
  test.use({ serviceWorkers: 'block' })

  const problem = (body: Record<string, unknown>) => ({
    status: body.status as number,
    contentType: 'application/problem+json',
    body: JSON.stringify({ type: 'about:blank', ...body }),
  })

  async function stubAndLaunch(page: Page, missionResponse: ReturnType<typeof problem>) {
    await page.route('**/api/v1/sourcing-requests', (r) =>
      r.fulfill({
        status: 201,
        json: {
          id: 'sr_1',
          status: 'normalized',
          spec: { description: 'PET bottle' },
          quantity_tiers: [{ quantity: 5000, priority: 'primary' }],
          delivery_country: 'ES',
          needs_clarification: [],
          created_at: '2026-11-09T09:00:00Z',
        },
      })
    )
    await page.route('**/api/v1/missions', (r) => r.fulfill(missionResponse))
    await requestMission(page)
    await page.getByRole('button', { name: 'Lanzar misión' }).click()
  }

  test('launch without an active financial snapshot is blocked and points to the CSV import (criterion 1)', async ({
    page,
  }) => {
    await stubAndLaunch(
      page,
      problem({ title: 'Conflict', status: 409, detail: 'No active financial snapshot' })
    )
    await expect(page.getByText('El snapshot financiero no está activo')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Importar CSV financiero' })).toBeVisible()
  })

  test('428 reauth_required sends the user to the step-up and never signs silently', async ({
    page,
  }) => {
    // Keycloak is not part of this suite: the redirect target is answered locally.
    await page.route('**/api/auth/signin**', (r) =>
      r.fulfill({ status: 200, contentType: 'text/html', body: 'step-up' })
    )
    await stubAndLaunch(
      page,
      problem({ title: 'Reauth', status: 428, error: 'reauth_required', reason: 'session_expired' })
    )
    await page.waitForURL(/\/api\/auth\/signin\?.*stepUp=1/)
  })
})

// Flows below run against the in-test API of fake-api.ts (page.route). MSW is blocked so it cannot answer first.
// The browser key, the Ed25519 signature and the countdown are real; only the server and Keycloak are stood in.
test.describe('signed flows', () => {
  test.use({ serviceWorkers: 'block' })

  async function setup(page: Page, over: Partial<Backend> = {}) {
    const b = newBackend(over)
    await page.clock.install({ time: new Date(NOW) })
    await installApi(page, b)
    await stubStepUp(page)
    return b
  }

  /** Opens a window from the signing screen; later navigation must be in-app so the in-memory window survives. */
  async function openWindow(page: Page) {
    await page.goto('/es/empresa/firma')
    await page.getByRole('button', { name: 'Abrir sesión de firma' }).first().click()
    await expect(page.getByText('3 firmas restantes').first()).toBeVisible()
  }

  test('open a signing session: browser key is enrolled, the window opens and the countdown shows', async ({
    page,
  }) => {
    const b = await setup(page)
    await openWindow(page)
    expect(b.keys).toHaveLength(1)
    expect(b.calls).toContain('POST /signing-sessions')
    await expect(page.getByRole('timer')).toHaveText(/^(15:00|14:5\d)$/)
  })

  test('several signatures inside the window: each is signed in the browser and the count goes down', async ({
    page,
  }) => {
    const b = await setup(page)
    for (const id of ['dec_a', 'dec_b'])
      b.decisions.set(id, pendingDecision(id, 'approve_purchase', `po-${id}`))
    b.approvals = ['dec_a', 'dec_b'].map((id) => ({
      id,
      status: 'sign',
      subject_ref: `po-${id}`,
      required_signers: 1,
      signatures: [],
      documents: [],
      tracking: [],
      created_at: NOW,
    }))
    await openWindow(page)
    for (const [n, id] of ['dec_a', 'dec_b'].entries()) {
      await page.getByRole('link', { name: 'Aprobaciones' }).first().click()
      await page.getByRole('link', { name: `po-${id}` }).click()
      await page.getByRole('button', { name: 'Primera firma' }).click()
      await expect(page.getByRole('status').filter({ hasText: 'Firmada.' })).toBeVisible()
      await expect(page.getByText(`${2 - n} firma`).first()).toBeVisible()
    }
    expect(b.signed.map((s) => s.id)).toEqual(['dec_a', 'dec_b'])
    // The signature the server received is a real Ed25519 signature by the key that was enrolled.
    expect(b.signed[0]!.body).toMatchObject({ key_id: b.keys[0]!.id, signing_session_id: 'ss_1' })
    expect(String(b.signed[0]!.body.signature).length).toBeGreaterThan(60)
  })

  test('window expiry with an injected clock turns the panel read-only and offers reauthentication', async ({
    page,
  }) => {
    await setup(page)
    await openWindow(page)
    await page.clock.fastForward('14:59')
    await expect(page.getByRole('timer')).toHaveText(/^00:/)
    await page.clock.fastForward('00:05')
    await expect(page.getByText('Sesión caducada').first()).toBeVisible()
    // No reload: the shell is still the signing screen, and reauth reopens a window.
    await expect(page).toHaveURL(/\/es\/empresa\/firma$/)
    await page.getByRole('button', { name: 'Reautenticar para firmar' }).click()
    await expect(page.getByRole('timer')).toHaveText(/^(15:00|14:5\d)$/)
  })

  test('dashboard: deals, server-side filters and an action that creates a decision', async ({
    page,
  }) => {
    const { deals, gate } = dashboardFixtures()
    const b = await setup(page, { deals, gate })
    await page.goto('/es/decisiones?vista=tratos')
    await expect(page.getByRole('link', { name: 'PET bottle 500 ml (ok)' })).toBeVisible()
    await expect(page.getByRole('link', { name: /\((anom|low)\)/ })).toHaveCount(2)

    // Filters go to the server and the list comes back filtered.
    await page.getByRole('combobox', { name: 'Plataforma' }).click()
    await page.getByRole('option', { name: 'mock-b' }).click()
    await expect(page).toHaveURL(/plataforma=mock-b/)
    await expect(page.getByRole('link', { name: /\(low\)/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /\(ok\)/ })).toHaveCount(0)
    await page.goto('/es/decisiones/d_ok?vista=tratos')

    // An allowed action creates a decision, then signing needs the window.
    await page.getByRole('button', { name: 'Seguir y comprar' }).click()
    await page.getByRole('button', { name: 'Crear decisión' }).click()
    await expect(page.getByText(/Decisión dec_1 creada/)).toBeVisible()
    expect(b.actions[0]).toMatchObject({
      path: '/dashboard/deals/d_ok/actions',
      body: { action: 'follow' },
    })
  })

  test('gate from an anomalous price: queued with its cause, follow is blocked with the API reason, unblock is signed in the browser', async ({
    page,
  }) => {
    const { deals, gate } = dashboardFixtures()
    const b = await setup(page, { deals, gate })
    await openWindow(page)
    await page.getByRole('link', { name: 'Decisiones' }).first().click()
    await page
      .getByRole('link', { name: /Cola de gate/ })
      .first()
      .click()
    const row = page.getByRole('row', { name: /PET bottle 500 ml \(anom\)/ })
    await expect(row).toContainText('Precio atípico')
    await row.getByRole('button', { name: 'Desbloquear' }).click()
    await page.getByRole('button', { name: 'Crear decisión' }).click()
    await expect(page.getByText(/Decisión dec_1 creada/)).toBeVisible()
    expect(b.signed).toHaveLength(0)
    await page.getByRole('button', { name: 'Firmar decisión' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Firmada.' })).toBeVisible()
    expect(b.signed.map((x) => x.id)).toEqual(['dec_1'])
    expect(b.actions[0]).toMatchObject({
      path: '/gate/queue/g_anom/actions',
      body: { action: 'unblock' },
    })
  })

  test('the anomalous deal cannot be followed: the button is disabled and the API reason is shown', async ({
    page,
  }) => {
    const { deals, gate } = dashboardFixtures()
    await setup(page, { deals, gate })
    await page.goto('/es/decisiones/d_anom')
    await expect(page.locator('li', { hasText: BLOCK_PRICE })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Seguir y comprar' })).toBeDisabled()
  })

  test('gate from a low-confidence seller: follow is blocked with the API reason', async ({
    page,
  }) => {
    const { deals, gate } = dashboardFixtures()
    await setup(page, { deals, gate })
    await page.goto('/es/decisiones/d_low')
    await expect(page.locator('li', { hasText: BLOCK_SELLER })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Seguir y comprar' })).toBeDisabled()
  })

  // The mock chat needs compose (orchestrator + browser worker + mock marketplace): here the transcript is MSW-style
  // fixture data behind the same UI, so this covers the approve-send interaction, not the worker.
  test('negotiation (against fixture data, not the compose mock chat): a drafted message is approved and then appears as sent', async ({
    page,
  }) => {
    const b = await setup(page, { deals: dashboardFixtures().deals })
    b.negotiation = {
      id: 'neg_1',
      offer_id: 'ok',
      strategy: 'volume_tiers',
      state: 'awaiting_approval',
      rounds: 1,
      max_rounds: 5,
      guardrail_hits: [],
      mission_id: 'ms_1',
      pending_draft: {
        id: 'dr_1',
        text: 'Could you quote 10.000 units with a volume tier?',
        source: 'llm',
        created_at: NOW,
      },
    }
    b.messages = [
      {
        id: 'm1',
        negotiation_id: 'neg_1',
        role: 'seller',
        content: 'Unit price is 12.00 EUR.',
        at: NOW,
      },
    ]
    await page.goto('/es/misiones/ms_1/negociaciones/neg_1')
    await expect(page.getByLabel('Texto del borrador')).toHaveValue(/10\.000 units/)
    // Not sent until the API confirms.
    await expect(page.getByText('Aún no se ha enviado')).toBeVisible()
    await page.getByRole('button', { name: 'Aprobar y enviar' }).click()
    await expect(
      page
        .getByRole('log')
        .locator('p', { hasText: 'Could you quote 10.000 units with a volume tier?' })
    ).toBeVisible()
    await expect(page.getByText('Aún no se ha enviado')).toHaveCount(0)
    await expect(page.getByLabel('Texto del borrador')).toHaveCount(0)
    expect(b.calls.filter((c) => c.endsWith('/approve'))).toHaveLength(1)
  })

  test('onboarding with CSV: upload, import report, requested activation signed with the browser key', async ({
    page,
    context,
  }) => {
    await signInAs(context, ['owner']) // the wizard is closed to the buyer role
    const b = await setup(page)
    const money = (amount_minor: number) => ({ amount_minor, currency: 'EUR' as const })
    b.financialImport = {
      id: 'imp_1',
      onboarding_id: 'ob_1',
      status: 'draft',
      csv_ref: 's3://csv/imp_1',
      created_at: NOW,
      report: {
        rows_ok: 11,
        rows_rejected: 1,
        rejections: [
          {
            row: 7,
            field: 'value_minor',
            reason_code: 'non_integer_amount',
            message: 'Row 7 amount is not an integer',
          },
        ],
        warnings: [],
        projection_enabled: false,
        periods_loaded: 1,
        reference_date: '2026-10-31',
        derived: {
          envelopes: [
            {
              category: 'packaging',
              allocated: money(10_000_000),
              spent: money(2_000_000),
              available: money(8_000_000),
              period_start: '2026-01-01',
              period_end: '2026-12-31',
            },
          ],
          net_buying_capacity: money(8_000_000),
          buying_power_score: null,
        },
      },
    }
    // The window is opened first and the wizard is reached by client-side navigation, so it survives (it lives in memory).
    await openWindow(page)
    await page.evaluate(() =>
      (window as unknown as { next: { router: { push: (p: string) => void } } }).next.router.push(
        '/es/onboarding/finanzas'
      )
    )
    await page
      .locator('input[type=file]')
      .setInputFiles({
        name: 'finanzas.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(
          'period,metric,value_minor,value_bp,currency,notes\n2026-10,cash_balance,100,,EUR,\n'
        ),
      })
    await page.getByRole('button', { name: 'Subir e importar' }).click()
    await expect(page.getByText('Ver informe completo')).toBeVisible()
    await page.getByRole('link', { name: 'Ver informe completo' }).click()
    await expect(page.getByText('Row 7 amount is not an integer')).toBeVisible()
    await page.getByRole('link', { name: 'Revisar resultado y activar' }).click()
    await expect(page.getByText('packaging')).toBeVisible()
    await page.getByRole('button', { name: 'Solicitar activación' }).click()
    await expect(
      page.getByText('Activación solicitada. Queda pendiente de tu firma.')
    ).toBeVisible()
    expect(b.signed).toHaveLength(0)
    await page.getByRole('button', { name: 'Activar con passkey' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Firmada.' })).toBeVisible()
    expect(b.signed.map((x) => x.id)).toEqual(['dec_act'])
  })
})
