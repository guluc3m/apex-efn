#!/usr/bin/env node
// Idempotently creates the dev feature flags in Unleash (project "default", environment "development").
// New flags are created DISABLED with a single "default" strategy, so enabling one is one toggle.
// Existing flags are never modified. Naming convention: docs/observability/flags.md.
//
// Usage (after `pnpm dev:up`):
//   node infra/unleash/seed-flags.mjs [extra.flag.name ...]
// Env: UNLEASH_URL (default http://localhost:4242/api), UNLEASH_ADMIN_TOKEN (dev default below).

const BASE_URL = (process.env.UNLEASH_URL ?? 'http://localhost:4242/api').replace(/\/+$/, '')
const ADMIN_TOKEN = process.env.UNLEASH_ADMIN_TOKEN ?? '*:*.apex-dev-unleash-admin'
const PROJECT = 'default'
const ENVIRONMENT = 'development'

const SEGMENT = '[a-z0-9_-]+'
const FLAG_PATTERNS = [
  new RegExp(`^platform\\.${SEGMENT}\\.enabled$`),
  new RegExp(`^negotiation\\.strategy\\.${SEGMENT}$`),
  /^negotiation\.autonomous_send$/,
  new RegExp(`^sanity\\.bands\\.${SEGMENT}$`),
  new RegExp(`^trust\\.model\\.${SEGMENT}$`),
]

// No platform is chosen yet (AGENTS.md Q10). The mock marketplace (D5-04) is the only one seeded.
const KNOWN_FLAGS = [
  'platform.mock-a.enabled',
  'platform.mock-b.enabled',
  'negotiation.autonomous_send',
]

const flagNames = [...new Set([...KNOWN_FLAGS, ...process.argv.slice(2)])]
for (const name of flagNames) {
  if (!FLAG_PATTERNS.some((pattern) => pattern.test(name))) {
    console.error(`malformed feature flag name "${name}"; see docs/observability/flags.md`)
    process.exit(2)
  }
}

const featureUrl = (name) =>
  `${BASE_URL}/admin/projects/${PROJECT}/features/${encodeURIComponent(name)}`

async function admin(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: {
      Authorization: ADMIN_TOKEN,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${method} ${url} -> HTTP ${response.status} ${text.slice(0, 300)}`)
  }
  return response.status === 204 ? null : response.json()
}

async function seedFlag(name) {
  const existing = await admin('GET', featureUrl(name))
  if (existing) {
    const env = existing.environments?.find((e) => e.name === ENVIRONMENT)
    console.log(
      `exists  ${name} (${ENVIRONMENT} enabled=${env?.enabled ?? 'unknown'}), left unchanged`
    )
    return
  }
  await admin('POST', `${BASE_URL}/admin/projects/${PROJECT}/features`, {
    name,
    type: 'release',
    description: 'Seeded by infra/unleash/seed-flags.mjs. Disabled until enabled deliberately.',
  })
  await admin('POST', `${featureUrl(name)}/environments/${ENVIRONMENT}/strategies`, {
    name: 'default',
    parameters: {},
    constraints: [],
  })
  console.log(`created ${name} (${ENVIRONMENT} disabled, default strategy added)`)
}

try {
  for (const name of flagNames) {
    await seedFlag(name)
  }
} catch (error) {
  const cause = error instanceof TypeError ? ` (${error.cause?.code ?? error.message})` : ''
  console.error(`seed failed${cause}: ${error.message}`)
  console.error(`is Unleash up at ${BASE_URL}? Try: pnpm dev:up`)
  process.exit(1)
}
