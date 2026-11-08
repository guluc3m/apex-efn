---
name: TRATO — Prompt de implementación (export)
description: Documento maestro exportable para un agente de código (Claude Code / Cursor / Devin) que debe construir desde cero TRATO, una plataforma B2B de sourcing inteligente y negociación automatizada de compras por volumen. Incluye descripción completa del producto, score de confianza del vendedor, validación de precios anómalos con gate humano, dashboard de decisión, firmas criptográficas Ed25519 con sesión de firma de 15 minutos, arquitectura multiagente, stack híbrido Next.js + Python/FastAPI/LangGraph + Node/Puppeteer con gateway LLM compatible con OpenAI para modelos autoalojados, modelo de datos, API, criterios de aceptación y roadmap por fases.
---

# TRATO — Prompt de implementación

Artefacto de exportación. El prompt limpio, listo para pegar en un agente de código, está en:

- **`PROMPT-IMPLEMENTACION.md`** — documento maestro completo (producto + agentes + stack + configuración + API + criterios de aceptación + roadmap + reglas de trabajo).
- **`NOTAS-TECH-LEAD.md`** — decisiones tomadas, supuestos y riesgos abiertos, para revisión humana. No forma parte del prompt.

## Uso

1. Copia el contenido íntegro de `PROMPT-IMPLEMENTACION.md`.
2. Pégalo como prompt de sistema / instrucciones iniciales del agente implementador.
3. Ejecuta por fases (Fase 0 → Fase 4). No permitas avanzar de fase sin que se cumplan los criterios de aceptación de la sección 9.
4. Mantén `NOTAS-TECH-LEAD.md` como documento de decisiones humanas: los ADRs que genere el agente deben contrastarse contra él.

## Alcance resumido

Plataforma B2B de compras por volumen que perfila a la empresa —incluida la carga de su situación financiera vía CSV—, busca ofertas multi-plataforma vía scraping, puntúa la confianza de cada vendedor a partir de su antigüedad, ventas, catálogo y reseñas, filtra precios anómalos con bandas estadísticas configurables, negocia precios de forma autónoma en el chat del vendedor con Puppeteer, contrasta cada oferta contra la capacidad financiera real de la empresa en EUR/USD/CNY y presenta los tratos finales en un dashboard donde un responsable humano decide, con firma criptográfica Ed25519 en sesión de firma de 15 minutos, qué ofertas seguir y comprar.

## Puntos clave que el implementador no debe suavizar

1. La confianza del vendedor es un cálculo determinista y versionado, no un juicio del LLM, y acompaña a cada oferta y a cada decisión firmada.
2. El control de precios anómalos ocurre **antes** de negociar: no se gasta presupuesto de negociación en ofertas fuera de rango.
3. Precio anómalamente barato + vendedor de baja confianza se escala de severidad, no se compensa.
4. Ninguna decisión avanza sin registro firmado verificable; el log de auditoría es una cadena de hashes en almacenamiento WORM.
5. La sesión de firma de 15 minutos reduce fricción, no el listón: caduca de forma fija, no deslizante, y los importes altos exigen reautenticación inmediata.
6. El acceso a modelos es HTTP compatible con OpenAI (`/v1/chat/completions`), sin endpoints propietarios, para permitir despliegue autoalojado.

---

# WORK SPLIT — SIX DEVELOPERS (parallel work protocol)

> This section is binding for every agent or human working on this repo. It splits all the work in
> `PROMPT-IMPLEMENTACION.md` into six **lanes** (DEV-1 … DEV-6). The lanes have exclusive file
> ownership, so people never edit the same files at the same time. If this section and
> `PROMPT-IMPLEMENTACION.md` disagree on product behaviour, `PROMPT-IMPLEMENTACION.md` wins. If they
> disagree on process (branches, ownership, PRs), this section wins.

## 0. Read this first (for agents)

1. **Find out which developer you are.** The human who starts your session tells you ("you are DEV-3").
   If nobody told you, **ask. Do not pick a lane yourself.**
2. **Only work on tasks in your lane** (section 5), and **only edit files your lane owns** (section 2).
   If you need a change in a file owned by someone else, follow section 3.5. Never "just fix it quickly".
3. **Picking the next task:** take the lowest-numbered task in your lane that is not merged yet and whose
   `Blocked by` tasks are all merged into `main`. To check whether a task is merged:
   `git fetch origin && git log origin/main --oneline --grep "<TASK-ID>"` (squash-merge titles always
   contain the task ID, see 3.3). Also check `gh pr list --search "<TASK-ID>" --state all` so you don't
   duplicate an open PR.
4. **One task = one branch = one PR.** If a task is too big for one PR (more than ~800 changed lines,
   excluding generated files and fixtures), split it into `<TASK-ID>a`, `<TASK-ID>b`, … in order.
5. **Tech Lead (TL) gates.** Tasks marked `TL approval: yes` touch money, price thresholds, seller
   confidence, signatures or compliance. For those: write the ADR **first**, open the PR as **Draft**
   with label `needs-tech-lead`, and **do not merge** without explicit TL approval on the PR. If you hit
   an open question from section 8, **stop that part and ask**. Never invent business numbers.
6. **No business defaults in code.** Every threshold, weight or limit from `PROMPT-IMPLEMENTACION.md` §7
   is read from versioned config (`config/defaults/` + DB). Engines receive config and the clock
   (`now`) as parameters. `new Date()`, `datetime.now()`, `Math.random()` or unseeded randomness inside
   deterministic code is a bug.
7. **Phase gates.** Every task has a phase (F0–F4) from the roadmap (`PROMPT-IMPLEMENTACION.md` §10).
   You may **develop** a task of phase N+1 on its branch and open it as a **Draft PR**, but you may
   **not merge** it until the git tag `phase-<N>-done` exists on `origin` (only the TL creates it,
   once the phase Definition of Done is met). Check with `git ls-remote --tags origin`.
8. **Never test against real marketplaces or paid models.** Use fixtures, the mock marketplace
   (D5-04) and the LLM stub (D4-02).

## 1. Lanes

| Lane | Name | Mission (one line) |
|---|---|---|
| **DEV-1** | Platform, DevOps & Identity | Repo tooling, CI/CD, local env, infra, observability, secrets, feature flags, login (OIDC/RBAC). |
| **DEV-2** | Data, Contracts, Signing & Audit | DB schema and migrations, RLS, OpenAPI contracts and codegen, Ed25519 keys, signing sessions, decisions, audit hash chain, WORM. |
| **DEV-3** | Deterministic Domain Engines | Money, FX, financial CSV import, landed cost and financial fit, seller confidence, price sanity, gate matrix 3.4.4, MCDA, all with shared TS/Python test vectors. |
| **DEV-4** | Orchestrator, Agents & LLM | FastAPI app shell, LLMGateway, LLM stub, prompts and evals, LangGraph graph, all agents except the negotiator, tenant config service, business endpoints. |
| **DEV-5** | Browser Automation & Negotiation | Browser worker, browser pool, PlatformAdapters, fixtures, mock marketplace and chat, negotiation engine and guardrails, takeover, compliance docs. |
| **DEV-6** | Frontend & UX | Next.js app, design system, onboarding wizard, mission UI, dashboard and gate queue, signing UX, i18n, Storybook, Playwright E2E. |

## 2. File ownership map

Only the owner edits these paths. Reviews from other lanes are welcome, edits are not (except through
section 3.5). D1-02 turns this table into `.github/CODEOWNERS`. If a path is not listed, ask DEV-1
before you create it.

| Path | Owner |
|---|---|
| `/package.json`, `/pnpm-workspace.yaml`, `/turbo.json`, `/tsconfig.json`, `/.prettierrc`, `/.prettierignore`, `/.gitignore`, `/.nvmrc`, `/.python-version`, `/.env.example`, `/compose.yaml` | DEV-1 |
| `/.github/**` (workflows, CODEOWNERS, templates, dependabot) | DEV-1 |
| `/infra/**` (compose files, Keycloak realm, Grafana dashboards, Helm, Terraform) except `/infra/mocks/**` | DEV-1 |
| `/packages/eslint-config/**`, `/packages/tsconfig/**` | DEV-1 |
| `apps/*/Dockerfile`, `apps/*/eslint.config.js` | DEV-1 |
| `apps/web/src/server/auth/**`, `apps/web/src/middleware.ts`, `apps/web/instrumentation.ts` | DEV-1 |
| `apps/orchestrator/src/trato/auth/**`, `apps/orchestrator/src/trato/platform/**` (vault, s3, redis, telemetry, flags clients) | DEV-1 |
| `apps/browser-worker/src/platform/**` (vault, telemetry, flags clients) | DEV-1 |
| `/tests/load/**` (k6) | DEV-1 |
| `/docs/observability/**`, `/docs/security/**` | DEV-1 |
| `/contracts/**` (OpenAPI 3.1 public and internal specs) | DEV-2 |
| `/packages/shared-types/**` (generated from `/contracts`, never hand-written DTOs) | DEV-2 |
| `/packages/crypto-client/**` | DEV-2 |
| `/packages/test-vectors/signing/**` | DEV-2 |
| `apps/web/prisma/**` (schema, migrations, seed) | DEV-2 |
| `apps/orchestrator/src/trato/db/**`, `trato/contracts/generated/**`, `trato/signing/**`, `trato/audit/**`, `trato/documents/**` | DEV-2 |
| `apps/orchestrator/src/trato/api/{signing,decisions,keys,audit}.py` | DEV-2 |
| `/packages/money/**`, `/packages/scoring/**` | DEV-3 |
| `/packages/test-vectors/**` except `signing/` | DEV-3 |
| `apps/orchestrator/src/trato/domain/**` (money, fx, finance, csv_import, trust, sanity, gate_matrix, mcda) | DEV-3 |
| `apps/orchestrator/pyproject.toml`, `src/trato/main.py`, `src/trato/config.py`, `src/trato/common/**` | DEV-4 |
| `apps/orchestrator/src/trato/api/__init__.py` and `api/{onboarding,sourcing,missions,sellers,dashboard,gate,config}.py` | DEV-4 |
| `apps/orchestrator/src/trato/{agents,llm,workers,tenant_config}/**`, `apps/orchestrator/prompts/**`, `apps/orchestrator/evals/**` | DEV-4 |
| `/apps/llm-stub/**`, `/infra/mocks/**` | DEV-4 |
| `/config/defaults/**` (versioned business defaults from spec §7; any change also needs TL approval) | DEV-4 |
| `/apps/browser-worker/**` except `src/platform/**`, `Dockerfile`, `eslint.config.js` | DEV-5 |
| `/apps/mock-marketplace/**` | DEV-5 |
| `apps/orchestrator/src/trato/negotiation/**`, `api/{negotiations,webhooks}.py` | DEV-5 |
| `/docs/compliance/**` | DEV-5 |
| `/apps/web/**` except the DEV-1 and DEV-2 paths listed above | DEV-6 |
| `/packages/ui/**` | DEV-6 |
| `apps/orchestrator/tests/<area>/**` | the owner of `<area>` (for example `tests/domain/**` belongs to DEV-3) |
| `/docs/adr/NNN-*.md` | whoever writes it, inside their number range (3.6) |
| `/docs/runbooks/<name>.md` | the lane whose task creates that runbook (see the tasks, and section 7 for criterion 31) |
| `/README.md`, `/AGENTS.md`, `/PROMPT-IMPLEMENTACION.md`, `/NOTAS-TECH-LEAD.md` | Tech Lead only (propose changes in a PR, TL merges) |

**Bootstrap exceptions (one-off):** D1-01 may touch config files in every package (lint, tsconfig,
package scripts) and D4-01 may create empty `__init__.py` package folders for every lane in the
orchestrator. Both must merge **before** other lanes edit those files. After they merge, the table
above applies with no exceptions.

## 3. Git and PR protocol

### 3.1 Branches
- `main` is protected: no direct pushes, no force-pushes. Changes go in only through PRs.
- Branch name: `dev<N>/<TASK-ID>-<short-kebab-slug>`, for example `dev3/D3-07-price-sanity-engine`.
- Always branch from the latest `origin/main`. Never branch from another developer's branch. If you
  need unmerged work from someone else, wait for it to merge, or code against the contract and the
  mocks (3.7).
- Only rebase or force-push **your own** branch, and always with `--force-with-lease`.

### 3.2 Step-by-step for every task
```bash
# 1. Start from a fresh main
git fetch origin
git checkout main
git pull --ff-only origin main

# 2. Create your branch
git checkout -b dev<N>/<TASK-ID>-<slug>

# 3. Work in small commits (Conventional Commits, scope = area, task ID in footer)
git commit -m "feat(scoring): add MAD fallback to IQR" -m "Task: D3-07"

# 4. Before opening or updating the PR, rebase onto the latest main
git fetch origin
git rebase origin/main
#    If pnpm-lock.yaml conflicts: never merge it by hand. Keep main's version and regenerate it, so
#    your own package.json changes are added back on top. During a rebase "--ours" means main:
#    git checkout --ours pnpm-lock.yaml && pnpm install && git add pnpm-lock.yaml && git rebase --continue

# 5. Run the checks your PR touches (all must pass locally)
pnpm lint && pnpm typecheck && pnpm test                      # TS
(cd apps/orchestrator && uv run ruff check . && uv run mypy src && uv run pytest)   # Python
pnpm contracts:check                                          # after D2-01 exists

# 6. Push and open the PR
git push -u origin dev<N>/<TASK-ID>-<slug>
gh pr create --base main --title "<TASK-ID>: <imperative summary>" --body-file .github/pull_request_template.md
#    Add "--draft" and "--label needs-tech-lead" when the task has TL approval: yes,
#    or when it belongs to a phase that is not open yet (rule 0.7).

# 7. After merge: delete the branch and move to the next task
git checkout main && git pull --ff-only && git branch -d dev<N>/<TASK-ID>-<slug>
```

### 3.3 PR rules
- **Title:** `<TASK-ID>: <summary>`, for example `D3-07: price sanity engine with MAD/IQR bands`. The
  squash-merge commit keeps this title, which is how other agents detect that a task is merged.
- **Merge method:** squash merge only. The author merges after approvals and green checks, except for
  `needs-tech-lead` PRs, where the TL merges.
- **Required approvals:** 1 reviewer from another lane, plus the code owner of every non-owned file
  touched (CODEOWNERS enforces this), plus the TL when the label is `needs-tech-lead`.
- **Required checks:** everything D1-04 marks as required (lint, typecheck, unit tests, contract drift,
  migration drift, LLM portability grep, secret scan, coverage gates).
- **PR body** (D1-02 creates `.github/pull_request_template.md` with this content):
  ```
  ## Task
  <TASK-ID> — link to the section of AGENTS.md
  ## What changed
  ## How it was tested (commands and results)
  ## Spec references (PROMPT-IMPLEMENTACION.md sections / acceptance criteria #)
  ## Contracts / schema touched? (link to the contract or schema PR if any)
  ## ADRs added or updated
  ## Risks and follow-ups
  ## Checklist
  - [ ] Only files owned by my lane (or approved cross-lane change)
  - [ ] No business defaults hardcoded; clock and config injected
  - [ ] No secrets or financial data in logs, fixtures or LLM context
  - [ ] Tests added (unit + property-based where money/bands/confidence/signatures)
  - [ ] Docs/runbooks updated
  ```
- Keep PRs focused: no drive-by refactors in other lanes, no formatting-only changes in files you don't own.

### 3.4 Commit and code conventions
- Conventional Commits: `feat|fix|refactor|test|docs|chore|ci|perf(scope): message`, footer `Task: <ID>`.
- TypeScript strict, ESM. Python 3.12, `ruff` and `mypy --strict` clean.
- Money is always integer minor units (int64). Never floats for money or FX.

### 3.5 Cross-lane changes (how to change something you don't own)
| You need… | Do this |
|---|---|
| A new or changed **API contract** (endpoint, DTO, queue payload) | Open a PR that **only** edits `/contracts/**`, title `<YOUR-TASK-ID>-contract: …`. DEV-2 must approve. Once merged, run `pnpm contracts:generate` on your branch. Never edit generated files by hand. |
| A **DB schema** change | Open a GitHub issue with label `schema-change` and the exact Prisma snippet. **Only DEV-2 writes migrations** (this avoids colliding migration timestamps). DEV-2 ships it as its own task `D2-SC-<issue#>`. |
| A **root/tooling** change (root package.json, turbo, CI, compose) | Open an issue with label `platform-request`. DEV-1 implements it. |
| A **new dependency in your own package** | Allowed. Add it to your package's `package.json` / `pyproject.toml` and justify heavy ones in an ADR (spec §11). |
| A **function from another lane** that doesn't exist yet | Agree on the signature in the issue tracker (label `interface`). The owner adds a stub with that signature, raising `NotImplementedError` / throwing, in a tiny PR. You code against the stub. |
| A **bug in another lane's code** | Open an issue with a failing test attached. Don't fix it in your PR. |

### 3.6 ADR numbering (prevents filename collisions)
ADRs live in `/docs/adr/NNN-title.md` using `000-template.md`. Each lane uses its own number range:
DEV-1 `100–199`, DEV-2 `200–299`, DEV-3 `300–399`, DEV-4 `400–499`, DEV-5 `500–599`, DEV-6 `600–699`,
TL `900–999`. Existing `001–003` stay as they are. Take the next free number in your range.

### 3.7 Contract-first, mock-first
- The public API is `/contracts/openapi.yaml`. The browser worker's internal API is
  `/contracts/internal/browser-worker.openapi.yaml`. Both are written before implementations.
- Frontend works against MSW mocks generated from the contract (D6-01). The orchestrator works against
  the LLM stub (D4-02) and the mock marketplace (D5-04). The browser worker works against fixtures.
- Lanes that call Python functions of other lanes use the interfaces in section 4. If the real code is
  not merged yet, use the stub (3.5).

### 3.8 Forbidden
- Pushing to `main`, force-pushing shared branches, merging your own `needs-tech-lead` PR.
- Editing generated files (`packages/shared-types/src/generated/**`, `trato/contracts/generated/**`).
- Writing DB migrations outside DEV-2.
- Hardcoding thresholds, weights or currency lists that belong to config.
- Sending human private keys to the server, or any "sign on server on behalf of the user" design.
- Calling proprietary LLM endpoints or SDKs without `base_url`.
- Scraping a platform whose ToS forbids it (document it in `/docs/compliance/` instead).

## 4. Integration seams (interfaces between lanes)

These are the agreed signatures. The owner creates them, and the consumers call them. Python
signatures are shown; the TS versions mirror them in camelCase. Types come from the generated contracts.

| Provider → Consumer | Interface |
|---|---|
| DEV-4 → all (Python) | `trato.common.clock.Clock` (`now() -> datetime`, injectable `FixedClock`), `trato.common.errors.Problem` (RFC 9457), `trato.common.idempotency` middleware, `trato.common.pagination.Cursor` |
| DEV-1 → DEV-2/4/5 | `trato.auth.deps.current_principal() -> Principal{user_id, tenant_id, roles}`, `require_role(*roles)`; `trato.platform.{vault,s3,redis,telemetry,flags}` clients; TS: `apps/web/src/server/auth/getSession()`, `getAccessToken()` |
| DEV-2 → DEV-4/5 | `trato.db.session.tenant_session(tenant_id)` (sets RLS `app.tenant_id`); `trato.signing.api.create_decision(type, subject_ref, payload) -> Decision`; `require_signed(decision_id) -> SignedDecision` (raises `PendingSignature`); `sign_service_event(service: str, payload) -> Signature`; `mark_session_risky(session_id, reason)`; `trato.audit.api.append(event)` |
| DEV-3 → DEV-4/5/6 | `trato.domain.money.Money`; `trato.domain.fx.convert(money, to, rates, now, cfg) -> Conversion` (carries `fx_provisional`); `trato.domain.finance.csv_import.parse(bytes, base_currency, rates, now) -> ImportResult{report, rows, derived}`; `trato.domain.finance.landed_cost(offer, qty, ctx) -> LandedCostBreakdown`; `financial_fit(breakdown, snapshot, cfg, now) -> FinancialFit`; `trato.domain.trust.compute(snapshot, cfg) -> SellerConfidence`; `trato.domain.sanity.check(offer_price_eur, reference, cfg) -> PriceSanityCheck`; `trato.domain.gate_matrix.combine(price_band, confidence_band, cfg) -> GateOutcome`; `trato.domain.mcda.rank(candidates, profile_weights, cfg) -> RankedRecommendation` |
| DEV-4 → DEV-5 | `trato.llm.LLMGateway.chat(role="negotiator", …)`; `trato.tenant_config.effective(tenant_id, category) -> EffectiveConfig` (with `config_version`); graph calls `trato.negotiation.node.negotiate_node(state)` |
| DEV-5 → DEV-4 | browser-worker internal HTTP API (contract file), `trato.negotiation.node.negotiate_node`, `trato.negotiation.api.takeover/resume/abort` |
| DEV-2/DEV-4/DEV-5 → DEV-6 | the public HTTP API only (`/contracts/openapi.yaml`); `@trato/crypto-client` for signing in the browser |

## 5. Task catalog

Format of each task: **ID — title** · Phase · Blocked by · TL approval · Steps · Done when.
"Blocked by" lists tasks that must be **merged** first. Tasks with no blockers can start right away.

---

### DEV-1 — Platform, DevOps & Identity

**D1-01 — Make the repo install, build and lint green** · F0 · Blocked by: none · TL: no
1. Generate and commit `pnpm-lock.yaml` (`pnpm install`). CI uses `--frozen-lockfile`.
2. Migrate ESLint to flat config (ESLint 9): `packages/eslint-config` exports flat-config arrays
   (`base`, `library`, `nextjs`). Add `eslint.config.js` to each app/package and remove the legacy `.js` style.
3. Add `prettier-plugin-tailwindcss` to root devDependencies, or remove it from `.prettierrc`.
4. Make `docker compose up` work from the repo root: create `/compose.yaml` that `include:`s
   `infra/docker-compose.yml`, and fix the root `docker:*` scripts.
5. Fix the Python CI job: `uv sync --extra dev` (or move dev deps to `[dependency-groups]` together with
   DEV-4), and add `apps/orchestrator/tests/test_smoke.py` hitting `/health` so pytest doesn't exit 5.
6. Make `pnpm build`, `pnpm lint` and `pnpm typecheck` pass on a clean checkout. Fix compile errors in
   other lanes' packages **only** when they are pure config/typing issues (bootstrap exception), and list them in the PR.
- Done when: a clean clone runs `pnpm install && pnpm build && pnpm lint && pnpm typecheck && pnpm test`
  plus the Python checks with zero errors, and CI is green on `main`.

**D1-02 — Repo governance files** · F0 · Blocked by: none · TL: no
1. `.github/CODEOWNERS` from the section 2 table. Ask the human for the GitHub handles of DEV-1…DEV-6 and the TL.
2. `.github/pull_request_template.md` (content in 3.3). Issue templates: `schema-change`,
   `contract-change`, `platform-request`, `interface`, `tl-question`, `bug`.
3. Labels: `needs-tech-lead`, `schema-change`, `contract-change`, `platform-request`, `interface`,
   `tl-question`, `lane:dev1`…`lane:dev6`, `phase:F0`…`phase:F4`.
4. `docs/runbooks/branch-protection.md`: settings for `main` (PR required, CODEOWNERS review, required
   checks, squash only, linear history, no force-push). Ask the human to apply them in GitHub.
- Done when: opening a PR auto-requests the right owners and shows the template.

**D1-03 — Complete local environment** · F0 · Blocked by: D1-01 · TL: no
1. Compose services: Postgres 16 **with pgvector** (`pgvector/pgvector:pg16`), Redis, MinIO, Keycloak,
   Langfuse, Vault (dev mode), Unleash, Grafana/Loki/Tempo/Prometheus, llm-stub (built from
   `apps/llm-stub`, D4-02), mock-marketplace (D5-04), and the app services.
2. **Separate databases** for Keycloak and Langfuse (init SQL creates `keycloak` and `langfuse` DBs).
   Today they share `trato`, which breaks Prisma migrations (Langfuse runs its own Prisma migrations).
3. MinIO bootstrap job: buckets `trato-attachments`, `trato-csv`, and `trato-audit` **with Object Lock**
   enabled (`mc mb --with-lock`), default retention in compliance mode.
4. Keycloak realm import (`infra/keycloak/realm-trato.json`): clients `trato-web` and
   `trato-orchestrator`, roles `owner|admin|buyer|finance|viewer`, MFA required, one test user per role and
   two tenants (for isolation tests).
5. Scripts: `pnpm dev:up`, `pnpm dev:down`, `pnpm dev:reset` (wipes volumes and reseeds). Document them in
   `docs/runbooks/local-dev.md`. Measure that a cold start takes under 10 minutes (spec §11).
- Done when: `docker compose up` starts everything healthy from a clean machine in under 10 minutes.

**D1-04 — CI pipeline with required gates** · F0 · Blocked by: D1-01 · TL: no
1. Path-filtered jobs per lane (turbo `--filter`), caching for pnpm and uv.
2. Docker-in-CI for Testcontainers (Postgres, Redis).
3. Coverage gate ≥ 80% on: `packages/money`, `packages/scoring`, `trato/domain/**`, `trato/signing/**`,
   `trato/negotiation/guardrails*`, `packages/crypto-client`.
4. Drift checks: `pnpm contracts:check` (D2-01) and `prisma migrate diff` (schema vs. migrations).
5. Improve the LLM portability grep (criterion 25): deny-list proprietary paths (`/assistants`,
   `/threads`, `/batches`, vendor SDK imports). Exclude the CI file itself and docs.
6. Secret scan (trufflehog/gitleaks), `pnpm audit`, `pip-audit`.
7. A Playwright E2E job that boots the compose stack (used by D6-08).
8. Write the list of required checks into `docs/runbooks/branch-protection.md`.
- Done when: every check runs on PRs, and the required ones block merge.

**D1-05 — Identity: OIDC login and RBAC** · F0 · Blocked by: D1-03, D4-01 · TL: no
1. Web: OIDC login against Keycloak in `apps/web/src/server/auth/**` and `src/middleware.ts` (protect
   app routes, refresh tokens, expose `getSession()` / `getAccessToken()` for the BFF).
2. Orchestrator: `trato/auth/**` validates JWTs via JWKS, resolves the tenant from the membership claim,
   and exposes `current_principal()` and `require_role(...)` FastAPI dependencies.
3. Enforce MFA in the realm. Write the RBAC matrix (which role may call which endpoint) in
   `docs/security/rbac.md`. `viewer` never signs. `override_discard` is limited to `finance|admin|owner`.
4. Tests: expired/forged tokens rejected, wrong tenant rejected, role checks.
- Done when: every orchestrator router can depend on `current_principal`, and the web app requires login.

**D1-06 — Secrets, Vault and KMS** · F0 · Blocked by: D1-03 · TL: no
1. `sops` + `age` setup (`.sops.yaml`) for secrets that live in the repo.
2. Vault dev: KV for marketplace credentials and browser session state (per tenant), Transit engine
   with **ed25519** keys for service signing keys (consumed by D2-07).
3. Clients: `trato/platform/vault.py`, `apps/browser-worker/src/platform/vault.ts`. Credentials are only
   referenced by opaque IDs (`CredentialRef`), never returned to the LLM or the browser.
- Done when: DEV-2 and DEV-5 can store and read secrets through the clients in tests.

**D1-07 — Observability and leak prevention** · F0 · Blocked by: D1-03 · TL: no
1. OpenTelemetry in all apps (`trato/platform/telemetry.py`, `apps/web/instrumentation.ts`, worker), exporting to Tempo/Loki/Prometheus. Add Sentry.
2. `docs/observability/metrics.md`: metric names and labels that each lane must emit (scraping health,
   price-band distribution, seller-confidence distribution, gate health, LLM health).
3. Grafana dashboards as code in `infra/grafana/` for those five areas.
4. A log redaction processor (structlog/pino) for secrets, tokens, credentials and financial values. A CI
   **leak test** (criterion 29) injects canary secrets/financial values and fails if they show up in logs or traces.
- Done when: the dashboards render with local data and the leak test runs in CI.

**D1-08 — Feature flags** · F0 · Blocked by: D1-03 · TL: no
1. Unleash in compose. Clients in `trato/platform/flags.py` and `browser-worker/src/platform/flags.ts`.
2. Naming convention in `docs/observability/flags.md`: `platform.<id>.enabled`,
   `negotiation.strategy.<id>`, `negotiation.autonomous_send`, `sanity.bands.<version>`, `trust.model.<version>`.
- Done when: a platform can be disabled by flag without code changes (verified by a DEV-5 test later).

**D1-09 — Container images and deployment** · F1 · Blocked by: D1-04 · TL: no
1. Multi-stage `Dockerfile` per app (non-root, pinned base images, Chromium image for the worker).
2. Helm charts (`infra/helm/`): separate node pool for browser-workers, optional GPU pool for self-hosted models.
3. Terraform (`infra/terraform/`): k8s cluster, Postgres, Redis, S3 with **Object Lock compliance mode**
   for audit, KMS, secrets manager.
4. A CD workflow to staging on merge to `main`.
- Done when: staging deploys from `main` automatically.

**D1-10 — Load tests** · F2 · Blocked by: D4-08, D4-11 · TL: no
1. k6 scripts in `tests/load/` for the orchestrator API, the mission queue and the gate queue (spec §5.11).
2. A nightly workflow with results published as artifacts.

---

### DEV-2 — Data, Contracts, Signing & Audit

**D2-01 — OpenAPI contracts and code generation** · F0 · Blocked by: none · TL: no
1. Write `/contracts/openapi.yaml` (OpenAPI 3.1) covering **every** endpoint in spec §8, plus the
   entities in spec §6. Common parts: `Idempotency-Key` header on all writes, cursor pagination,
   `application/problem+json` errors, `428 {error:"reauth_required", reason}`, the closed `Currency`
   enum `EUR|USD|CNY`, and money as `{amount_minor: int64, currency}`.
2. Write a skeleton for `/contracts/internal/browser-worker.openapi.yaml` (DEV-5 fills the details in D5-01 via a contract PR).
3. Codegen: TS + Zod into `packages/shared-types/src/generated/` and Pydantic v2 into
   `apps/orchestrator/src/trato/contracts/generated/`. Root scripts `pnpm contracts:generate` and
   `pnpm contracts:check` (ask DEV-1 to add them through a `platform-request`, or include them in this PR with DEV-1's review).
4. Replace the hand-written DTOs in `packages/shared-types/src/*.ts` with re-exports of the generated
   types. They duplicate the contract, which spec §5.1 forbids. Keep only constants that aren't DTOs.
5. ADR-200: tooling choice and versioning rules for contracts.
- Done when: both languages compile against the generated types and `contracts:check` fails on drift.

**D2-02 — ADRs: migration ownership and where endpoints live** · F0 · Blocked by: none · TL: **yes**
1. ADR-201: Prisma Migrate is the single owner of DDL. SQLAlchemy maps the same tables and never
   migrates. Alembic is not used for DDL. (The spec lists both tools but requires a single owner.)
2. ADR-202: business endpoints live in the orchestrator. The Next.js BFF only handles auth/session,
   proxies, and SSE passthrough. No business logic in the BFF.
- Done when: the TL approves both ADRs.

**D2-03 — Schema v1 and first migration** · F0 · Blocked by: D2-02 · TL: **yes**
1. Fix scaffold defects in `apps/web/prisma/schema.prisma`:
   - Money columns as `BigInt` (int64). Today they are `Int` (int32 overflows at about 21M EUR in cents).
   - FX rates as `Decimal`, never `Float`. Discount and percentage fields in basis points (`Int`) or `Decimal`.
   - A Postgres enum `Currency {EUR USD CNY}` on every currency column.
   - Polymorphic actors: `SigningKey.ownerId` and `Decision.decidedBy` must allow **service** actors.
     Today both are FKs to `User`, so service keys and automatic decisions can't be stored.
   - Add the missing entities from spec §6: `BudgetEnvelope`, `FinancialImport`, parsed financial rows,
     `ConnectedAccount`, `CredentialRef`, `UserProfilePreference`, `PricingThresholdConfig`,
     `ConfidenceModelConfig`, `ScoringWeightsConfig` (all **versioned** with `config_version`, plus the
     signature of the decision that created them), `ReviewAnomaly`, `Recommendation`, `ScoreBreakdown`,
     `Approval`, `SourcingItem`, `SourcingPlan`, `WebAuthnCredential`.
   - `TenantConfig` is a single mutable row today. Turn it into append-only versions.
2. Enable pgvector, and add embedding tables for products and negotiation history.
3. Append-only triggers: block `UPDATE`/`DELETE` on `audit_events`, `signatures`, `fx_rates`,
   `seller_signal_snapshots`, `seller_confidences`, and on financial snapshots once they are `active`/`superseded`.
4. Seed script: two tenants and users matching the Keycloak test users. Config is **not** seeded here.
   D4-03 provides `python -m trato.tenant_config.load_defaults`, and DEV-1's `dev:reset` runs it after
   this seed (this avoids a circular dependency between D2-03 and D4-03).
- Done when: `prisma migrate dev` runs from scratch, and the triggers are covered by tests.

**D2-04 — Row-level security and tenant isolation test** · F0 · Blocked by: D2-03 · TL: no
1. Add `tenant_id` to every tenant-scoped table, with RLS policies using `current_setting('app.tenant_id')`.
   App DB role is not superuser and not table owner. A separate migrator role runs migrations.
2. Helpers that set the tenant per transaction: a Prisma client extension (web) and a SQLAlchemy session event (`trato/db/session.py`).
3. **Criterion 30:** an automated test (Testcontainers) that enumerates every tenant table, writes as
   tenant A, and asserts tenant B reads and writes nothing.
- Done when: the isolation test runs in CI and covers every table automatically, including new ones.

**D2-05 — SQLAlchemy data layer** · F0 · Blocked by: D2-03, D4-01 · TL: no
1. SQLAlchemy 2 async models in `trato/db/models/` mapped to the Prisma schema. Session factory, and `tenant_session()`.
2. CI test: migrate a DB with Prisma, then reflect it and compare with the SQLAlchemy metadata (fails on drift).
- Done when: DEV-3/4/5 can persist and read entities through `trato.db`.

**D2-06 — Canonical JSON, hashing and signature test vectors** · F0 · Blocked by: D2-01 · TL: **yes**
1. RFC 8785 JCS in TS (`packages/crypto-client/src/jcs.ts`, already drafted) and in Python (`trato/signing/jcs.py`).
2. Shared vectors in `packages/test-vectors/signing/`: the RFC 8785 examples, unicode, number edge
   cases, nested objects, and Ed25519 vectors from RFC 8032. Both runners must produce identical bytes and hashes.
3. Property-based tests (fast-check and hypothesis): canonicalize(parse(canonicalize(x))) == canonicalize(x).
- Done when: TS and Python agree byte-for-byte on every vector.

**D2-07 — Signing keys (human and service)** · F0 · Blocked by: D2-05, D2-06, D1-06 · TL: **yes**
1. ADR-203: browser Ed25519 support. WebCrypto Ed25519 is not available on every browser version. If it
   is unsupported, **block signing with a clear message**. A server-held human key is never a fallback.
   Key backup/escrow is optional and off by default (TL open question).
2. Finish `@trato/crypto-client`: non-exportable key generation, IndexedDB storage, signing over the
   canonical payload, tests (Node webcrypto + `fake-indexeddb`). Remove `new Date()` (inject a clock).
3. Endpoints: `GET/POST /v1/keys/me` (register a public key), `POST /v1/keys/{id}/revoke`. Revocation and
   rotation are themselves signed decisions that need immediate reauth. Revoking never invalidates past signatures.
4. Service keys: Vault Transit Ed25519 per service/agent, registered as `owner_type=service`.
- Done when: a user can enroll a key, revoke it, and old signatures still verify with the historical key.

**D2-08 — Signing sessions (15-minute fixed window)** · F0 · Blocked by: D2-07, D1-05 · TL: **yes**
1. ADR-204: WebAuthn relying party in the orchestrator (`py_webauthn`) vs. Keycloak step-up (ACR). Propose one and get TL approval.
2. `POST/GET/DELETE /v1/signing-sessions`. State in Redis, plus a Postgres copy for audit.
   `expires_at = auth_at + signing.session_minutes`, a **fixed** window that signing never extends.
   `max_decisions_per_session` enforced.
3. Invalidation on: expiry, logout, key revocation or rotation, device fingerprint change, ASN/country
   jump, reaching the max, and `mark_session_risky()` (called by the GateAgent).
4. Every invalid case returns `428 {error:"reauth_required", reason}`.
5. Tests with an injected clock and no sleeps: criteria **19, 20, 22**.
- Done when: those criteria pass in CI.

**D2-09 — Decisions, signatures, hash chain and dual control** · F0 · Blocked by: D2-08 · TL: **yes**
1. `POST /v1/decisions` (creates a decision with its canonical payload, status `pending_signature`),
   `POST /v1/decisions/{id}/sign`, `POST /v1/decisions/{id}/verify`.
2. Payload builders per decision type. A gate decision payload **must** include the amount, the offer,
   the `PriceSanityCheck`, `SellerConfidence{score, band, model_version}`, the financial verdict and `config_version`.
3. The server verifies the signature **before** persisting. It checks that the session is alive, the key is
   not revoked, and the device matches. The `Signature` row stores `signing_session_id` and `auth_at`.
4. Per-tenant hash chain: `prev_signature_hash`, serialized with a per-tenant advisory lock.
5. Immediate reauth (ignores the window) for: amount > `signing.high_value_reauth_above`, snapshot
   activation, threshold or weight changes, discard overrides, and key operations.
6. Dual control: above `approval.dual_control_above`, two signatures from **different** signers are required.
7. `trato.signing.api` for other lanes: `create_decision`, `require_signed`, `sign_service_event`.
8. Tests: criteria **17, 18, 21, 23**, including tamper tests (flip one byte, change the score in the payload).
- Done when: those criteria pass and an unsigned decision can't move an offer to `purchased`.

**D2-10 — Audit log and WORM anchoring** · F0 · Blocked by: D2-09 · TL: **yes**
1. `trato/audit/**`: an append-only hash-chained `AuditEvent` writer for every agent and human action.
2. `GET /v1/audit` (admin/compliance roles only) and `GET /v1/audit/verify` (full chain re-verification).
   A periodic re-verify function (DEV-4 schedules it).
3. Anchor the chain head to S3 Object Lock (compliance mode). RFC 3161 timestamping is optional (F4).
4. Runbooks: `key-loss.md`, `signing-session-blocked.md`, `audit-chain-broken.md`.
- Done when: tampering with any row is detected by `/v1/audit/verify`.

**D2-11 — Documents: RFQ, purchase order, verification certificate** · F2 · Blocked by: D2-09, D4-11 · TL: no
1. PDF generation in `trato/documents/`: RFQ, purchase order, and a signature verification certificate
   that includes signature hashes and the seller's confidence **at decision time**.
- Done when: the PDFs embed verifiable hashes, checked by a test.

**D2-12 — GDPR tooling** · F2 · Blocked by: D2-04 · TL: **yes**
1. Retention policies per data class, export per data subject, and erasure that keeps the audit chain verifiable (document the approach in an ADR).

**D2-13 — Analytics store** · F3 · Blocked by: D2-05 · TL: no
1. ClickHouse + dbt marts for price history, benchmarks and savings, which feed the sanity reference (spec §3.3.1 item 3).

---

### DEV-3 — Deterministic Domain Engines

> The scaffold engines in `packages/money` and `packages/scoring` are **drafts, not trusted code**.
> They contain invented constants and bugs (see section 6). Rewrite them test-first against the spec.
> Python (`trato/domain/**`) is the runtime authority for decisions. The TS packages mirror it for UI
> display and what-if previews. **Both must pass the same vectors.**

**D3-01 — Shared test-vector framework and injected clock** · F0 · Blocked by: D1-01 · TL: no
1. `packages/test-vectors/` with a JSON format (`{name, input, config, expected}`) and a JSON schema.
   Runners for Vitest and Pytest that load every file under a folder.
2. ADR-300: vector format, float tolerance policy (exact for money, documented epsilon for statistics), and the clock-injection rule.
3. Remove `new Date()` from `packages/money`, `packages/scoring` (engines take `now` or the timestamp as input).
- Done when: one sample vector runs green in both languages in CI.

**D3-02 — Money arithmetic (TS + Python)** · F0 · Blocked by: D3-01 · TL: **yes**
1. int64 minor units. TS: ADR-301 decides between `bigint` and `number` with a `MAX_SAFE_INTEGER` guard.
   Python: `int` plus a range check.
2. A single documented rounding rule ("half-up to the destination minor unit"). **Ask the TL** how
   half-up applies to negative amounts (section 8, Q1). JS `Math.round(-2.5) === -2` is not "away from zero".
3. Remove the `fromMajor(number)` float path, and parse from decimal strings instead. `multiply`/`allocate`
   use integer or rational math. Allocation always sums exactly.
4. Property tests (fast-check, hypothesis) plus shared vectors.
- Done when: the same vectors pass in TS and Python, and coverage is ≥ 80%.

**D3-03 — FX engine and rate ingestion** · F0 · Blocked by: D3-02, D2-05 · TL: **yes**
1. Rates as decimal strings or rationals. EUR pivot, and triangulation using the **same source and timestamp**.
2. Stale rates (> `fx.max_age_hours`) return a conversion flagged `fx_provisional=true`. They do not
   return `null` like the scaffold. Unsupported currencies are rejected.
3. Conversion records `original_amount`, `original_currency`, `fx_rate`, `fx_as_of`, `fx_source`, `converted`.
4. `trato/domain/fx/ingest.py`: fetch daily rates (ADR-302 proposes ECB reference rates, TL confirms the
   source, section 8 Q6) into the immutable `FxRate` history. DEV-4 schedules it.
5. Tests: criterion **24**, round-trip and triangulation properties.
- Done when: the vectors pass in both languages.

**D3-04 — Financial CSV importer** · F1 · Blocked by: D3-03 · TL: **yes**
1. `trato/domain/finance/csv_import.py`: UTF-8, separator autodetection (`,` `;` `\t`), the exact columns
   and closed metric enum from spec §3.1.1, per-row rejection with reasons, rejecting the later duplicate
   (not the whole file), currency conversion with `converted=true`, `projection_enabled` rules (1 period
   with `cash_balance` minimum, 3 periods for projection).
2. Derived values: envelopes per category, net buying capacity, reference date. The **BuyingPowerScore**
   formula is not specified, so **ask the TL** (section 8, Q2).
3. It never activates anything. It returns `ImportResult`. Activation is a signed decision (DEV-4 + DEV-2).
4. Fixture CSVs (valid, invalid rows, duplicates, mixed currencies, wrong decimals) in `packages/test-vectors/finance/`.
- Done when: criteria **2** and **24** pass at the engine level.

**D3-05 — Landed cost and financial fit** · F1 · Blocked by: D3-03 · TL: **yes**
1. Line-by-line `LandedCostBreakdown`: unit price × quantity, shipping, insurance, duties and import VAT,
   cost of capital for the payment term, payment fees, FX and FX-risk. The duty/VAT data source and cost of
   capital rate are open (section 8, Q5). Take them as inputs, never as constants.
2. A property test that the lines add up to the total **to the cent** (criterion **4**).
3. `financial_fit`: compares against the envelope, projected treasury at payment date, credit line and
   safety buffer. Verdict `within_budget|stretch|out_of_budget` with numeric reasons. The `financials_stale` flag follows spec §3.5.
- Done when: criterion 4 passes, and the verdict vectors pass in both languages.

**D3-06 — Seller confidence engine** · F1 · Blocked by: D3-01 · TL: **yes**
1. Rewrite against spec §3.4.2 step by step: saturated log/linear normalization with `x_sat` **per signal
   from config**, Bayesian rating shrinkage, the Wilson lower bound (correct z for the configured
   confidence level), structural manipulation flags (burst z-score, abnormal 5-star share, low
   verified share, duplicate/generic text, spikes around account creation). Any flag **caps the band at `low`**.
   Disputes/refunds above `seller.max_dispute_rate` get a proportional penalty.
2. Bands from config: `untrusted` when score < `band_low` **or** < `hard_block_below`. The scaffold wrongly
   returns `low` between 20 and 25. Return `insufficient_data` when signals < `seller.min_signals`. Define
   "signal count" vs. `data_completeness` in ADR-303 (section 8, Q3).
3. `model_version` in the output. Bit-for-bit reproducible from the snapshot plus config.
4. ADR-304 proposes default weights per signal group (institutional > volume, per the TL notes) for TL approval.
5. Fixtures: 1 review at 5.0 vs. 500 at 4.8 (criterion **7**), review burst (**8**), insufficient data
   (**9**), determinism vectors (**6**).
- Done when: criteria 6–9 pass in both languages.

**D3-07 — Price sanity engine** · F1 · Blocked by: D3-03 · TL: **yes**
1. Rewrite against spec §3.3: reference universe (mission offers, 12-month history, category benchmark)
   using landed cost per unit in EUR. Reference weights are open (section 8, Q4), so take them from config.
2. `min_sample` → `insufficient_reference` → decision follows `sanity.on_insufficient_reference`.
3. Median + MAD, falling back to IQR, then to relative deviation. Modified z-score. Asymmetric `low_side_factor`.
   Relative bounds `max_relative_rise/drop`. Absolute floor/ceiling prevails. The ">60% below median ⇒ at
   least atypical" rule. Legitimate-cause check returning **enum causes only**.
4. Remove scaffold inventions: the `× 1.5` "implausible" rule, `sampleSize: 0`, and
   `referencePriceEur = offer price`. Implement exactly the spec bands.
5. `config_version` in the output. Fixture with a −90% and a +200% outlier (criterion **5**).
- Done when: criterion 5 passes at the engine level in both languages.

**D3-08 — Gate combination matrix (spec §3.4.4)** · F1 · Blocked by: D3-06, D3-07 · TL: **yes**
1. A pure function `combine(price_band, confidence_band, cfg)` covering the 3×3 table plus
   `insufficient_reference` and `insufficient_data`. Cheap-atypical + low confidence escalates to
   discard. `seller.escalate_cheap_low_confidence` is respected.
2. An exhaustive table test of all combinations (criterion **10**).
- Done when: criterion 10 passes in both languages.

**D3-09 — MCDA scoring and ranking** · F1 · Blocked by: D3-05, D3-06, D3-08 · TL: **yes**
1. Hard constraints as a **pre-filter** with visible reasons: certifications, banned countries, budget,
   MOQ, price band, confidence band.
2. Documented monotonic `f()` per criterion. `w3` uses the seller confidence score. Weights come from the
   profile. Penalties. Contribution breakdown per criterion.
3. Remove scaffold inventions (neutral `0.5` margin, `0.8` spec match). Missing inputs are explicit
   "unknown" with a documented treatment that the TL approves.
4. Invariant tests: `out_of_budget` never #1 (criterion **15**), `low` seller never #1 (**11**), and a
   profile switch reorders deterministically with an explanation diff (**27**).
- Done when: those invariants pass in both languages.

**D3-10 — Trust model calibration and treasury projection** · F3 · Blocked by: D2-13 · TL: **yes**
1. Per-category calibration tooling. Multi-period treasury projection from historical CSVs.

---

### DEV-4 — Orchestrator, Agents & LLM

**D4-01 — Orchestrator app shell (unblocks other lanes)** · F0 · Blocked by: none · TL: no
1. Fix `pyproject.toml`: `[tool.ruff.lint]` section, dev dependency group consistent with CI (coordinate with D1-01).
2. Create empty packages for every lane so nobody creates them concurrently: `trato/{common,auth,platform,
   db,contracts,signing,audit,documents,domain,tenant_config,agents,llm,workers,negotiation}/__init__.py`.
3. Register **all** routers from spec §8 in `api/__init__.py` with `501 Not Implemented` stubs:
   onboarding, sourcing-requests, missions, sellers, dashboard, gate, negotiations, signing-sessions,
   decisions, keys, audit, webhooks, config. Each router file then belongs to the lane in section 2, so
   nobody needs to touch `api/__init__.py` again.
4. `trato/common/`: injectable `Clock`, ID generation, RFC 9457 problem+json handler, `Idempotency-Key`
   middleware (Redis-backed), cursor pagination helpers.
5. Fix `agents/graph.py` typing (it returns a compiled graph but is annotated `StateGraph`). Make `mypy --strict` pass.
- Done when: the app boots, `/health` works, every §8 route answers 501, and the CI Python job is green.

**D4-02 — OpenAI-compatible LLM stub** · F0 · Blocked by: D4-01 · TL: no
1. `apps/llm-stub/`: a small FastAPI server with `/v1/chat/completions`, `/v1/embeddings`, `/v1/models`,
   driven by scenario fixtures (matched by role/prompt hash): toggle `json_schema` support, return malformed
   JSON, tool calls, latency, 5xx, timeouts, streaming.
2. It replaces the Mockoon file in `infra/mocks/`. DEV-1 wires it into compose.
- Done when: the gateway tests (D4-04) run entirely against it, without network access.

**D4-03 — Tenant configuration service** · F0 · Blocked by: D2-05 · TL: **yes**
1. `/config/defaults/tenant-config.v1.json` with the defaults from spec §7. Keys marked "sin definir" stay
   **unset** and must be filled by the tenant. Never invent them.
2. `trato/tenant_config/`: resolves effective config (global → tenant → category override), returns `config_version`.
   Also ships the CLI `python -m trato.tenant_config.load_defaults` that writes config v1 for the seeded tenants (used by `dev:reset`).
3. `api/config.py`: read the effective config, and propose a change. **A change is a signed decision**
   (DEV-2) that needs immediate reauth and creates a new version. Add the endpoints to `/contracts` via a contract PR (they are not in §8).
4. Test: changing `sanity.z_gate` changes the classification without a deploy and produces a signed decision (criterion **5**, together with D3-07).
- Done when: engines can be called with `effective(tenant, category)`, and the config history is reproducible.

**D4-04 — LLMGateway (spec §5.6)** · F0 · Blocked by: D4-02, D4-03 · TL: no
1. Per-role endpoint config `{base_url, api_key_ref, model, capabilities, timeout, max_output, temperature, seed}` from `llm.roles.*`.
2. Declared capability profiles. Never assume undeclared capabilities.
3. The structured-output ladder, steps 1–5, with Pydantic validation at each step. A failure is a loud
   error, never a silent default (criterion **26**).
4. Retries with jitter, a circuit breaker per endpoint, a fallback chain, and a **hard token budget per mission** (criterion **28**).
5. Accounting into `LLMEvent` plus Langfuse (tokens, latency p50/p95, JSON repair rate, cost or GPU-seconds).
6. A redaction guard: credentials and financial values never enter prompts (criterion **29**, together with D1-07).
7. CI matrix against small self-hosted engines (vLLM / llama.cpp / Ollama `/v1`) behind a flag (criterion **25**). Ask DEV-1 for the CI job.
- Done when: criteria 25, 26 and 28 pass against the stub.

**D4-05 — Prompts and evaluation suite** · F1 · Blocked by: D4-04 · TL: no
1. `apps/orchestrator/prompts/*.jinja`, versioned (the version goes into `LLMEvent`). No model-specific tricks.
2. A promptfoo or DeepEval suite in `apps/orchestrator/evals/` with golden sets per role. It runs in CI against **every** configured endpoint. A prompt change can't merge if any endpoint fails.

**D4-06 — LangGraph mission graph** · F1 · Blocked by: D4-04, D2-09 · TL: **yes**
1. Per-offer state machine exactly as spec §4 (`discovered → … → purchased`). Postgres checkpointer. Resumable, idempotent transitions (no duplicate messages or signatures on resume).
2. Every relevant transition emits `sign_service_event` plus an audit event (DEV-2 APIs).
3. The invariant **trust + sanity → negotiation** is enforced by the graph structure. A test asserts the
   negotiation adapter call counter is 0 for `atypical|implausible|insufficient_reference` without a signed unblock (criterion **12**).
4. Human gates use LangGraph interrupts that resume only after `require_signed()` succeeds.

**D4-07 — Onboarding: IntakeAgent and endpoints** · F1 · Blocked by: D4-06, D3-04 · TL: **yes**
1. `/v1/onboarding/sessions` (conversational profiling plus a progressive form backend).
2. `/v1/onboarding/{id}/financial-csv` stores the original in S3 and calls the DEV-3 importer. The LLM
   writes the `warnings[]` text from the structured report only. The LLM may **suggest** header mappings, and the user confirms them.
3. `/financial-csv/activate` requires a signed decision with immediate reauth. All-or-nothing activation.
   Earlier snapshots become `superseded` (immutable).
4. Onboarding is complete only with an `active` snapshot. Mission launch is blocked otherwise (criterion **1**).
   Mark `financials_stale` after `finance.stale_after_days`.
5. Runbook `financial-snapshot-stale.md`.

**D4-08 — Sourcing: PlannerAgent, missions and SSE** · F1 · Blocked by: D4-06 · TL: no
1. `POST /v1/sourcing-requests`. NL → `SourcingRequest` through structured output.
2. PlannerAgent builds a `SourcingPlan`, respects adapter `transport` and the platform feature flags.
3. `POST /v1/missions`, `GET /v1/missions/{id}`, and SSE `GET /v1/missions/{id}/events` (progress and live transcript).

**D4-09 — Scraping orchestration and EnrichmentAgent** · F1 · Blocked by: D4-08, D5-01, D5-04, D3-03 · TL: no
1. Dispatch jobs to the browser worker's internal API, then collect `Offer` and `RawSellerSignals`.
2. Normalize, dedupe across platforms, translate specs, and convert currency at ingestion through DEV-3 FX. Persist.
3. Criterion **3** in mock mode: ≥ 3 offers from ≥ 2 platforms in < 30 s in CI (against D5-04).

**D4-10 — Trust, Sanity and Finance agent nodes** · F1 · Blocked by: D4-09, D3-05, D3-06, D3-07 · TL: no
1. Thin nodes that call DEV-3 functions with `effective()` config and persist results. Recompute a seller
   snapshot when it is older than `seller.snapshot_max_age_days`.
2. `GET /v1/sellers/{id}/confidence` (with history), `POST …/recompute` (audited), `GET /v1/missions/{id}/offers`
   (each offer with `SellerConfidence`, `PriceSanityCheck` and `FinancialFit`).

**D4-11 — GateAgent, gate queue and dashboard endpoints** · F1 · Blocked by: D4-10, D3-08, D2-09 · TL: **yes**
1. Combine through `gate_matrix.combine`. Build `GateQueueItem`s for every cause listed in spec §3.8, with `gate.sla_hours` and reminders.
2. `GET /v1/gate/queue`, `GET /v1/dashboard/deals` (filters for bands, verdict, platform, signature status),
   `POST /v1/dashboard/deals/{id}/actions` (`follow|renegotiate|takeover|hold|discard`). Every action is a
   signed decision. `discard` requires a closed reason code plus a comment.
   `POST /v1/gate/queue/{id}/actions` (`unblock|override_discard`): `unblock` lets an offer held in the queue proceed,
   `override_discard` reverses a discard (`finance|admin|owner` only). Both are signed decisions.
3. Blocking rules: `atypical` or `low` can't go to purchase without an unblocking signed decision (criterion **11**).
   `gate.max_renegotiations`. `financials_stale` blocks direct purchase. `fx_provisional` requires extra
   confirmation. The response explains **why** an action is blocked (criterion **16** data).
4. Can call `mark_session_risky()` on anomalies.

**D4-12 — EvaluatorAgent and recommendation** · F1 · Blocked by: D4-10, D3-09 · TL: no
1. `GET /v1/missions/{id}/recommendation?profile=…` calls DEV-3 MCDA. The LLM narrates from the numbers
   and never ranks. Includes the trade-off comparison and savings vs. list price and market median.

**D4-13 — SupervisorAgent and background workers** · F1 · Blocked by: D4-06 · TL: no
1. ADR-400: Celery vs. Arq.
2. Scheduled jobs: FX ingestion (D3-03), audit chain re-verification (D2-10), gate SLA reminders, seller snapshot refresh, stale financials marking.
3. SupervisorAgent: stuck-mission detection, cost control against the token budget, escalation.

**D4-14 — Post-decision flows** · F2 · Blocked by: D4-11, D2-11 · TL: no
1. Approvals inbox with dual control, RFQ/PO triggers, and price memory ("last time you gave it to me at X") written to `PriceHistory` and fed back into the sanity reference.

---

### DEV-5 — Browser Automation & Negotiation

**D5-01 — Browser worker foundation and internal API** · F0 · Blocked by: D2-01, D1-01 · TL: no
1. Fill in `/contracts/internal/browser-worker.openapi.yaml` through a contract PR (DEV-2 approves):
   search, product, seller, seller-signals jobs, plus chat session ops (open, send, read, screenshot, takeover lock).
2. Implement the internal HTTP API, backed by BullMQ queues (priorities, retries, DLQ, trace ID per mission).
   Per-domain concurrency queues with exponential backoff.
3. Validate config with zod. Fix the scaffold typo `allowCounterpartites` → `allowCounterparts`.
- Done when: the orchestrator can enqueue a mock job and get a typed result.

**D5-02 — Browser pool and account sessions** · F1 · Blocked by: D5-01, D1-06 · TL: no
1. A Chromium pool with memory limits, recycling by page count, and a watchdog. `puppeteer-extra` stealth.
   Playwright as an alternative per adapter.
2. Session persistence per account (cookies/storage encrypted in Vault). Detection of invalidated sessions
   plus a human-assisted reauth flow. A proxy abstraction (residential/datacenter).
3. Credentials stay inside the worker. The orchestrator and the LLM only see an opaque `account_id`.

**D5-03 — PlatformAdapter framework** · F1 · Blocked by: D5-01, D1-08 · TL: no
1. Finalize the interface (`search`, `getProduct`, `getSeller`, `getSellerSignals`, `openChat`,
   `sendMessage`, `readMessages`) and `transport: http|browser`. Output uses the generated types only.
   Adapters return **raw** signals, and normalization belongs to DEV-3.
2. An adapter registry gated by `platform.<id>.enabled` (a test proves a disabled platform is never called).
3. A fixture harness (recorded HTML/JSON, replay mode) and a reusable **adapter contract test suite** that every adapter must pass.

**D5-04 — Mock marketplace and simulated seller chat** · F1 · Blocked by: D5-01 · TL: no
1. `apps/mock-marketplace/`: two fake platforms with products, sellers and a chat.
2. Fixtures covering: manipulated-review sellers, insufficient-data sellers, solid sellers (1×5.0 vs.
   500×4.8), and offers with −90%/+200% outliers.
3. Scripted chat personas: aggressive, evasive, asks for off-platform payment or contact details, offers
   anomalously low prices, replies in Chinese, truncated replies, quotes in unsupported currencies.
- Done when: DEV-4 criterion 3 and DEV-6 E2E can run entirely against it.

**D5-05 — Adapter #1 (official API)** · F1 · Blocked by: D5-03 · TL: **yes**
1. The TL picks the platform (section 8, Q10). Write `/docs/compliance/<platform>.md` first (ToS, rate limits, data collected and why).
2. Implement it with fixtures, contract suite, flag, and seller-signal mapping.

**D5-06 — Adapter #2 (scraping)** · F1 · Blocked by: D5-03 · TL: **yes**
1. Compliance doc first. If the ToS forbid automation, **don't implement it**: document why and propose an alternative.
2. Respect `robots.txt` and rate limits. Prefer `transport: http`, and use the browser only for login/chat.
3. Fixtures include manipulated-review sellers. Contract suite, flag.

**D5-07 — Negotiation engine and guardrails** · F1 · Blocked by: D5-04, D4-04, D3-07 · TL: **yes**
1. `trato/negotiation/`: a playbook state machine for spec §3.6 steps 1–8 (open with context, justified
   anchor, ask for volume tiers first, decreasing counter-offer ladder up to `target_discount`, authorized
   counterparts only, detect closing signals, written summary, ask for EUR/USD/CNY if the currency is unsupported).
2. **Deterministic guardrails** checked on every drafted message **before** sending: never exceed
   `max_discount` or the requested volume, no prepayment/guarantees/terms/penalties without profile
   authorization, max rounds/tokens per conversation, max messages/hour per account, escalate to a human on
   sensitive-data or off-platform payment requests. The agent never accepts a binding commitment.
3. The LLM (role `negotiator` through `LLMGateway`) only drafts text and extracts the seller's offer into
   structured output. Prices and limits are decided in code.
4. Re-check every quoted price with DEV-3 sanity. If it is `atypical`/`implausible`, stop and send it to the gate (criterion **13**).
5. Phase 1 mode is **semi-automatic**: each drafted message waits for human approval (add an approve-send endpoint through a contract PR).
6. Full transcript plus screenshots stored in S3. `NegotiationOutcome`. Graph node `negotiate_node(state)`.

**D5-08 — Takeover, resume, abort and anti-abuse** · F1 · Blocked by: D5-07 · TL: no
1. `POST /v1/negotiations/{id}/takeover|resume|abort` (`api/negotiations.py`). A lock guarantees the agent never sends while a human holds control, and it stops cleanly.
2. Never contact the same seller from simultaneous missions. Rate limit per seller account.

**D5-09 — Adversarial negotiation suite** · F1 · Blocked by: D5-07 · TL: **yes**
1. Run every mock persona in CI. Assert no `max_discount` breach, no unauthorized concessions, escalation on
   off-platform payment requests, and a stop on anomalous prices (criterion **14**). The TL notes call this "the heart of the product".

**D5-10 — Runbooks and scraping health metrics** · F1 · Blocked by: D5-03, D1-07 · TL: no
1. Runbooks: `platform-session-invalidated.md`, `captcha-persistent.md`, `dom-change.md`, `platform-signals-missing.md`.
2. Emit the scraping health metrics defined in `docs/observability/metrics.md`.

**D5-11 — Autonomous mode, more platforms, webhooks** · F2 · Blocked by: D5-09 · TL: **yes**
1. Autonomous sending on one real platform behind `negotiation.autonomous_send`. Third and fourth adapters. `POST /v1/webhooks/platforms/{platform}`.

**D5-12 — Cross-platform seller identity resolution** · F3 · Blocked by: D5-11 · TL: **yes**

---

### DEV-6 — Frontend & UX

> The UI never computes business results (money, bands, scores, eligibility). It displays what the API
> returns. `@trato/scoring` may only be used for **previews** that pass the same vectors, and the API stays authoritative.

**D6-01 — Web foundation** · F0 · Blocked by: D1-01, D2-01 · TL: no
1. Fix Tailwind v4: use `@tailwindcss/postcss` in `postcss.config.js` and a CSS-first `@theme` in
   `globals.css`. Delete `tailwind.config.ts`, or load it with `@config`. Today the build fails.
2. next-intl with `es`, `en`, `zh` message files and locale routing from day one.
3. A typed API client from the generated contract, TanStack Query setup, Zustand UI stores, a
   problem+json error mapper, and a global `428 reauth_required` handler hook (used by D6-03).
4. MSW handlers generated from the OpenAPI examples, so screens can be built before the backend exists.
5. BFF route handlers in `apps/web/src/app/api/**` that only proxy to the orchestrator (token from DEV-1's `getAccessToken()`), generate `Idempotency-Key`, and pass SSE through.
- Done when: `pnpm --filter @trato/web build` passes and a mocked page renders in three languages.

**D6-02 — Design system** · F0 · Blocked by: D6-01 · TL: no
1. Storybook for `packages/ui`. Add Table (TanStack), Dialog, Tabs, Select, Toast, Tooltip, DropdownMenu, Popover.
2. Domain display components: `PriceBandBadge`, `ConfidenceBandBadge` (with signal breakdown popover),
   `FinancialVerdictBadge`, `SignatureStatusBadge` (signed/pending/invalid), `MoneyDisplay` (format only), `DisabledReason` tooltip.
3. Accessibility checks (axe) in Storybook.

**D6-03 — Signing UX** · F0 · Blocked by: D6-02, D2-08 · TL: **yes**
1. Key enrollment with `@trato/crypto-client`, and the passkey (WebAuthn) ceremony that opens a signing session.
2. A persistent header indicator: signer, countdown `mm:ss` computed from the server `expires_at` (corrected
   for clock offset), and signatures remaining. On expiry the panel switches to read-only with a
   "re-authenticate to sign" button, **without a reload or lost context**.
3. On `428`: open the passkey flow, then retry. Never sign silently, never degrade to unauthenticated.
4. Playwright tests with a virtual authenticator (CDP WebAuthn) and an injected clock (UI side of criteria **19–22**).

**D6-04 — Onboarding wizard** · F1 · Blocked by: D6-03, D4-07 · TL: no
1. A multi-step form (React Hook Form + Zod from generated schemas): fiscal identity, sector, connected
   accounts (credentials are posted straight to the backend vault endpoint and never kept in client state),
   budget and base currency, purchase policy, negotiation parameters, and **effective thresholds shown read-only**.
2. A conversational panel with the IntakeAgent.
3. CSV upload → `ImportReport` view with per-row rejections and warnings, header-mapping confirmation, and activation through a signed decision.
4. Show the BuyingPowerScore and envelopes.

**D6-05 — Mission UI** · F1 · Blocked by: D6-02, D4-08 · TL: no
1. Create a sourcing request in natural language, live progress via SSE, and a live negotiation transcript.
2. Offers matrix (TanStack Table) with seller confidence **always next to the price**, and filters by band, verdict and platform.

**D6-05b — Negotiation message approval** · F1 · Blocked by: D6-05, D5-07 · TL: no
1. In the live transcript, show each message drafted by the agent as awaiting approval (Phase 1 semi-automatic mode, D5-07 step 5).
2. Approve and send through the approve-send endpoint that D5-07 adds to the contract. Nothing is presented as sent until the API confirms it.
- Done when: a drafted message from the mock chat can be approved in the UI and then appears as sent in the transcript.

**D6-06 — Deals dashboard and gate queue** · F1 · Blocked by: D6-03, D4-11, D4-12 · TL: no
1. Per-deal content from spec §3.8 (everything listed, including confidence breakdown, landed cost
   breakdown, sanity explanation, transcript, and score contributions).
2. Actions `follow|renegotiate|takeover|hold|discard` (with a reason code for discard), plus `unblock|override_discard`
   on gate items when the API offers them, through signed
   decisions. Disabled buttons explain why, using the API's reason (criterion **16**).
3. Gate queue with SLA countdowns. A comparison view with explicit trade-offs. Savings widgets. A price
   distribution chart with the sanity band marked (Recharts).
4. Switching the profile re-ranks in place and shows why (criterion **27**, UI side).

**D6-07a — Minimal takeover panel** · F1 · Blocked by: D6-06, D5-08 · TL: no
1. Chat panel opened by the `takeover` action: take control, send messages as a human, resume the agent, abort (D5-08 endpoints).
- Done when: a human can take over a negotiation against the mock chat, and the agent sends nothing while they hold control.

**D6-07 — Approvals and verification views** · F2 · Blocked by: D6-06, D2-11 · TL: no
1. Approvals inbox with dual control, PDF downloads, and signature/audit verification views.

**D6-08 — End-to-end suite** · F1 · Blocked by: D6-05b, D6-06, D1-04, D5-04 · TL: no
1. Playwright E2E for the flows in spec §5.11: onboarding with CSV, mission, gate from an anomalous price, gate
   from a low-confidence seller, negotiation against the mock chat, dashboard, opening a signing session,
   multiple signatures inside the window, window expiry with an injected clock, and reauth.

## 6. Known defects in the current scaffold (already assigned)

The scaffold was generated quickly and is **not** spec-compliant in these places. Each item is fixed in the task shown.

| Defect | Where | Fixed in |
|---|---|---|
| No `pnpm-lock.yaml`, but CI uses `--frozen-lockfile` | `.github/workflows/ci.yml` | D1-01 |
| ESLint 9 with legacy configs, so `eslint src/` fails | `packages/eslint-config`, all packages | D1-01 |
| `prettier-plugin-tailwindcss` used but not installed | `.prettierrc` | D1-01 |
| `docker compose up` from the root finds no compose file | root scripts, `infra/` | D1-01 |
| `uv sync --dev` doesn't install `[project.optional-dependencies].dev`, and pytest has no tests | CI, `pyproject.toml` | D1-01 / D4-01 |
| Keycloak and Langfuse share the app database (breaks Prisma migrations) | `infra/docker-compose.yml` | D1-03 |
| Mockoon stub can't simulate structured-output degradation | `infra/mocks/` | D4-02 |
| Hand-written DTOs duplicate the contract (spec §5.1 forbids it) | `packages/shared-types/src/*` | D2-01 |
| Money columns `Int` (int32), FX `Float`, currency `String` | `schema.prisma` | D2-03 |
| Service keys/decisions impossible (`ownerId`/`decidedBy` FK to `User`) | `schema.prisma` | D2-03 |
| Config not versioned. Missing entities from spec §6 | `schema.prisma` | D2-03 |
| `new Date()` inside engines (non-injected clock) | `packages/money`, `packages/scoring`, `crypto-client` | D3-01 / D2-07 |
| Float paths in money (`fromMajor`, `multiply`), unclear negative rounding | `packages/money/src/money.ts` | D3-02 |
| Stale FX returns `null` instead of `fx_provisional` | `packages/money/src/fx.ts` | D3-03 |
| Wrong `untrusted` band (scores 20–24 return `low`), hardcoded constants | `packages/scoring/src/seller/*` | D3-06 |
| Invented `× 1.5` implausible rule, `sampleSize: 0`, `referencePriceEur = price` | `packages/scoring/src/sanity/engine.ts` | D3-07 |
| Invented MCDA defaults (`0.5` margin, `0.8` spec match), no hard-constraint pre-filter | `packages/scoring/src/mcda/engine.ts` | D3-09 |
| Graph return type wrong for `mypy --strict` | `trato/agents/graph.py` | D4-01 |
| Gateway has no capabilities, retries, fallback, budget or accounting | `trato/llm/gateway.py` | D4-04 |
| Typo `allowCounterpartites` | `browser-worker/src/jobs/negotiation.ts` | D5-01 |
| Tailwind v4 set up with v3-style config and PostCSS plugin (build fails) | `apps/web` | D6-01 |

## 7. Acceptance criteria → owner (spec §9)

| # | Owner (supporting) | | # | Owner (supporting) |
|---|---|---|---|---|
| 1 | DEV-4 D4-07 (DEV-3, DEV-6) | | 17 | DEV-2 D2-09 |
| 2 | DEV-3 D3-04 (DEV-4) | | 18 | DEV-2 D2-09 |
| 3 | DEV-4 D4-09 (DEV-5) | | 19 | DEV-2 D2-08 (DEV-6 D6-03) |
| 4 | DEV-3 D3-05 | | 20 | DEV-2 D2-08 |
| 5 | DEV-3 D3-07 + DEV-4 D4-03 | | 21 | DEV-2 D2-09 (DEV-6) |
| 6 | DEV-3 D3-06 | | 22 | DEV-2 D2-08 |
| 7 | DEV-3 D3-06 | | 23 | DEV-2 D2-09 / D2-10 |
| 8 | DEV-3 D3-06 | | 24 | DEV-3 D3-03 / D3-04 |
| 9 | DEV-3 D3-06 (DEV-6 D6-06) | | 25 | DEV-4 D4-04 (DEV-1 D1-04) |
| 10 | DEV-3 D3-08 | | 26 | DEV-4 D4-04 |
| 11 | DEV-3 D3-09 + DEV-4 D4-11 | | 27 | DEV-3 D3-09 (DEV-6 D6-06) |
| 12 | DEV-4 D4-06 (DEV-5) | | 28 | DEV-4 D4-04 |
| 13 | DEV-5 D5-07 | | 29 | DEV-1 D1-07 + DEV-4 D4-04 |
| 14 | DEV-5 D5-09 | | 30 | DEV-2 D2-04 |
| 15 | DEV-3 D3-09 | | 31 | Runbooks: DEV-5 (session invalidated, CAPTCHA, DOM change, seller signals missing), DEV-2 (key loss, signing session blocked, audit chain broken), DEV-4 (financial snapshot stale) |
| 16 | DEV-6 D6-06 (DEV-4 D4-11) | | | |

## 8. Open questions for the Tech Lead (blocking: stop and ask)

If your task depends on one of these, implement the mechanism with the value **injected from
config/fixtures**, open a `tl-question` issue referencing the ID, and keep the PR in Draft until it is answered.

| ID | Question | Blocks |
|---|---|---|
| Q1 | "Half-up" rounding for negative amounts: away from zero, or toward +∞? | D3-02 |
| Q2 | BuyingPowerScore formula, and how envelopes are derived from the CSV | D3-04 |
| Q3 | Seller default weights, `x_sat` per signal, and whether `seller.min_signals` counts signals or is a ratio | D3-06 |
| Q4 | Weights of the sanity reference universe (mission / history / benchmark) | D3-07 |
| Q5 | Source of duties/import VAT data and the cost-of-capital rate | D3-05 |
| Q6 | FX source (proposal: ECB reference rates) | D3-03 |
| Q7 | Values for `approval.threshold`, `approval.dual_control_above`, `signing.high_value_reauth_above`, `neg.target_discount`/`max_discount` per category | D2-09, D4-11, D5-07 |
| Q8 | Threshold for "`stretch` above threshold" going to the gate (spec §3.8) | D4-11 |
| Q9 | Migration owner: Prisma Migrate only (ADR-201)? | D2-02 |
| Q10 | Which platforms for adapter #1 (official API) and #2 (scraping), and who signs the compliance docs | D5-05, D5-06 |
| Q11 | WebAuthn RP in the orchestrator vs. Keycloak step-up | D2-08 |
| Q12 | `insufficient_reference`: block (current) or negotiate with a warning | D3-07, D4-03 |
| Q13 | New-seller policy: systematic gate or a looser threshold | D3-06, D4-11 |
| Q14 | Is platform KYC/escrow a hard requirement to buy? | D3-09 |
| Q15 | Are counterparts (prepayment, framework contract) allowed in the MVP? | D5-07 |
| Q16 | Key escrow: offered or not | D2-07 |

## 9. Dependency waves (order, not dates)

- **Wave 0 (start immediately, in parallel):** D1-01, D1-02, D2-01, D2-02, D4-01. Then D1-03, D1-04, D3-01, D4-02.
  DEV-6 starts D6-01 as soon as D1-01 and D2-01 merge. DEV-5 starts D5-01 after D2-01.
- **Wave 1 (Phase 0 core):** D1-05…D1-08, D2-03…D2-10, D3-02, D3-03, D4-03, D4-04, D6-02, D6-03.
  The TL tags `phase-0-done` when the Phase 0 DoD holds.
- **Wave 2 (Phase 1, may be drafted earlier per rule 0.7):** every F1 task, following its `Blocked by`.
  The TL tags `phase-1-done` when criteria 1–31 that apply to the MVP pass.
- **Wave 3+ (F2–F4):** the remaining tasks, plus roadmap Phase 3–4 items (calibration, ClickHouse/dbt,
  self-hosted models in production, RFC 3161 anchoring, enterprise SSO, PSD2). The TL assigns these to a lane when that phase opens.

