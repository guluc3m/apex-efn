# Feature flags

Owner: DEV-1 (task D1-08). Provider: Unleash 8.x (compose service `unleash`, port 4242). Clients:

- Python: `apps/orchestrator/src/trato/platform/flags.py` (`UnleashFlags`, `StaticFlags`, `FlagProvider`).
- TypeScript: `apps/browser-worker/src/platform/flags.ts` (`UnleashFlags`, `StaticFlags`, `FlagProvider`).

Both clients have the same behaviour. Change them together.

## 1. Naming convention

Flag names are dot-separated segments. Each segment uses `[a-z0-9_-]+`. Versions are written without dots
(`v1`, `v2`, `2026q1`). The names below are the only valid families. Any other name is rejected with an
error, both by the clients and by the seed script. A typo therefore fails loudly in development and
never turns silently off.

| Pattern                       | Example                             | Meaning                                                                      | Owner (consumer)                          |
| ----------------------------- | ----------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------------- |
| `platform.<id>.enabled`       | `platform.mock-a.enabled`           | A marketplace adapter may be called (search, product, chat).                 | DEV-5 (adapter registry, D5-03)           |
| `negotiation.strategy.<id>`   | `negotiation.strategy.anchor-first` | A negotiation playbook variant is available.                                 | DEV-5 (D5-07)                             |
| `negotiation.autonomous_send` | `negotiation.autonomous_send`       | The agent may send messages without per-message human approval. Kill switch. | DEV-5 (D5-07, D5-11)                      |
| `sanity.bands.<version>`      | `sanity.bands.v1`                   | A version of the price-sanity band configuration is active.                  | DEV-3 engine, DEV-4 config (D3-07, D4-03) |
| `trust.model.<version>`       | `trust.model.v1`                    | A version of the seller-confidence model is active.                          | DEV-3 engine, DEV-4 config (D3-06)        |

The `<id>` segment of `platform.<id>.enabled` is the platform id used by the adapters, for example
`mock-a`. Use the same id in the adapter code, the registry and the flag.

## 2. Defaults: fail closed

**Every flag is OFF unless it is explicitly enabled.** This applies in four cases:

- the flag is not in Unleash (unknown);
- the toggle is disabled in the environment;
- Unleash is unreachable and no snapshot has ever been fetched;
- a strategy cannot be evaluated (see section 4).

**Why:** a marketplace must never be scraped or contacted unless someone has enabled it (ToS and
compliance, PROMPT-IMPLEMENTACION.md §5.9). Autonomous sending must never switch on by accident.

**No exceptions.** A consumer that needs "on by default" must invert the flag, for example
`negotiation.autonomous_send` is an off-by-default kill switch. Do not change the default in code.

**Unreachable Unleash:** the client keeps the last good snapshot. Network and HTTP errors never throw out of
`is_enabled` / `isEnabled`. They are logged as a warning with the error class and message only. The
client token is never logged.

## 3. Clients

```python
from trato.platform.flags import UnleashFlags

flags = UnleashFlags.from_env(app_name="trato-orchestrator")   # UNLEASH_URL, UNLEASH_API_TOKEN
flags.refresh()                                                 # once at start-up, and on a schedule
if flags.is_platform_enabled("mock-a"):
    ...
```

```ts
import { UnleashFlags } from './platform/flags'

const flags = UnleashFlags.fromEnv(process.env) // UNLEASH_URL, UNLEASH_API_TOKEN
await flags.refresh()
const stop = flags.startPolling(60_000) // long-running worker: keep the snapshot fresh
if (flags.isPlatformEnabled('mock-a')) {
  /* ... */
}
```

Settings:

- `UNLEASH_URL`: the value from `.env.example` ends in `/api` (for example `http://localhost:4242/api`).
  A trailing slash is accepted. The client calls `GET {UNLEASH_URL}/client/features`.
- `UNLEASH_API_TOKEN`: a **client** token (`<project>:<environment>.<secret>`). Never an admin token.
- Headers sent: `Authorization: <token>`, `UNLEASH-APPNAME`, `UNLEASH-INSTANCEID`.
- Timeout: 5 seconds per request.
- Polling: the Python client exposes `async poll(interval_seconds, stop_event)`. The TS client exposes
  `startPolling(intervalMs)`, which returns a stop function. Both reuse `refresh()`.

**Tests:** inject a `FlagProvider` instead of a live client. Python: `StaticFlags({"platform.mock-a.enabled": True})`.
TS: `new StaticFlags({ 'platform.mock-a.enabled': true })`. Both raise on malformed names.

## 4. Evaluation rules

Unleash semantics, with the supported subset:

1. Toggle missing, or `enabled: false` in the environment → **off**.
2. Toggle enabled with **no strategies** → **on**.
3. Otherwise the strategies are OR-ed. The first one that evaluates to true turns the flag on.
4. Per strategy:
   - `disabled: true` → off.
   - Has **constraints** or **segments** → off (not implemented; fails closed).
   - `default` → on.
   - `flexibleRollout` with `rollout` = `100` → on. `rollout` = `0` → off. Any other percentage →
     off and logged once (sticky hashing is not implemented).
   - `userWithId`, `applicationHostname`, `remoteAddress`, any other strategy → off and logged once.
5. Variants and context are not implemented. Context arguments are accepted but unused.

Partial rollouts are not supported on purpose. A partial rollout would mean a platform is contacted for only
some requests, and nobody has agreed how to choose those requests. If a need appears, add a new ADR
before adding hashing.

## 5. Ownership of the snapshot

- The orchestrator and the browser worker each hold their own snapshot.
- A flag change in Unleash reaches a running process after its next `refresh()` (the browser worker: one
  polling interval, 60 seconds in the example above). Disabling a platform therefore needs no deploy.
- The disable path for a platform is: switch `platform.<id>.enabled` off in Unleash. D5-03 proves in a test
  that a disabled platform's adapter is never called.

## 6. Local setup

- Seed the known flags after the stack is up: `node infra/unleash/seed-flags.mjs`. See
  `docs/runbooks/local-dev.md`.
- Seeded flags: `platform.mock-a.enabled`, `platform.mock-b.enabled`, `negotiation.autonomous_send`. All
  created **disabled**, each with one `default` strategy. Extra names can be given on the command line.
- The seed script never changes an existing flag. It only creates missing ones.
- Development tokens (public placeholders, see `infra/docker-compose.yml`):
  - client: `default:development.trato-dev-unleash-client` (value of `UNLEASH_API_TOKEN`);
  - admin: `*:*.trato-dev-unleash-admin` (the seed script's default).

## 7. Out of scope (this version)

- Official Unleash SDKs (they need manifest changes in several lanes).
- Sticky percentage rollouts, constraints, segments, variants, and the metrics and impression APIs.
- Admin operations from the apps. Admin changes are made in the Unleash UI or through the admin API.
- Whether a flag change must go through a signed decision (DEV-2) is **not decided here**. Open a
  `tl-question` issue before any flag starts gating money or compliance behaviour.
