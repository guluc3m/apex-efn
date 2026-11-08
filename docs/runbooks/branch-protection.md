# Branch protection for `main`

Owner: DEV-1. Task: D1-02 (governance) and D1-04 (required checks).

This runbook describes the settings we want on `main`, what can be applied today, and how to apply the rest.

## Current limitations (verified)

These facts were checked against the GitHub API on the repository itself:

1. The repository is **private** and the organisation is on the **free plan**.
2. Branch protection and repository rulesets return **403** with "Upgrade to GitHub Pro or make this repository public". The `main` branch cannot be protected today.
3. CODEOWNERS is only **enforced** (review required, reviews auto-requested) on private repositories with GitHub Pro, Team or Enterprise, or on public repositories. The file `.github/CODEOWNERS` is in place, but on this plan it does not request reviews or block merges.
4. GitHub Actions is **disabled for this repository by organisation policy**: the organisation allows Actions only for "selected repositories", and this repository is not selected. The CI jobs in `.github/workflows/ci.yml` do not run, so no required status check can report a result. An organisation admin can fix this under **Organisation Settings → Actions → General → Policies** by adding this repository to the selected list. On the free plan, runs for private repositories consume the organisation's shared Actions minutes.

Consequence: until one of the options below is chosen, the rules in this file are enforced **by convention** only. Every author must still get one approval from another lane, and the Tech Lead must merge `needs-tech-lead` PRs.

## Options

| Option                                                                         | What it unlocks                                                      | Cost / impact                                                                                                            |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| A. Upgrade the organisation to Team (or the account to Pro for personal repos) | Branch protection, rulesets, CODEOWNERS enforcement, required checks | Paid. Decision for the human owner.                                                                                      |
| B. Make the repository public                                                  | Same features as A, on the free plan                                 | Exposes code, ADRs and runbooks publicly. Needs an explicit decision (the spec contains business and compliance detail). |
| C. Enforce by convention and apply what is free                                | Squash-only merges, auto-delete of head branches                     | No merge blocking. Relies on discipline and on the PR template checklist.                                                |

Option C is available now. Options A and B are needed for real enforcement.

## Intended settings for `main`

Apply these once option A or B is in place. Use a branch ruleset (Settings → Rules → Rulesets) or classic branch protection, whichever the plan offers.

- Require a pull request before merging.
  - Required approving reviews: **1**.
  - Require review from Code Owners: **on**. This applies the `.github/CODEOWNERS` file.
  - Dismiss stale pull request approvals when new commits are pushed: **on**.
  - Require approval of the most recent reviewable push: **on**, if the plan offers it.
- Require status checks to pass before merging, and require branches to be up to date before merging.
  - Required status check: **`CI OK`**, the single aggregate job. See "Required checks" below for the full list and the reasons.
- Require linear history: **on** (squash merges only produce linear history).
- Block force pushes: **on**.
- Block deletion of `main`: **on**.
- Bypass list: empty. Any exception is a decision for the Tech Lead and must be recorded in an issue.

## Required checks

Job names come from `.github/workflows/ci.yml`. Check names in a ruleset must match them exactly.

**Recommended: require only `CI OK`.** It is an aggregate job that needs every gate and fails if any of them
failed or was cancelled. Adding a gate later means editing one `needs:` list in the workflow, not the ruleset.

| Job name (check name)         | Required?                   | Notes                                                                                               |
| ----------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------- |
| `CI OK`                       | **Yes (recommended)**       | Aggregate. Passes only if every needed job succeeded or was skipped.                                |
| `TypeScript`                  | Only if listed individually | Build, lint, typecheck, test (affected packages on PRs, all on `main`), plus the 80% coverage gate. |
| `Python`                      | Only if listed individually | `ruff`, `mypy`, unit tests, 80% coverage gate for the modules that exist.                           |
| `Integration tests`           | Only if listed individually | Testcontainers, runs `pytest -m integration`.                                                       |
| `Secret scan`                 | Only if listed individually | TruffleHog, verified secrets only, pinned to `v3.99.8`.                                             |
| `LLM Portability Check`       | Only if listed individually | Criterion 25. Deny-list grep, self-tested with `--self-test`.                                       |
| `Contracts drift`             | Only if listed individually | Skips until `contracts:check` exists (D2-01).                                                       |
| `Migration drift`             | Only if listed individually | Skips until `apps/web/prisma/migrations` exists (D2-03).                                            |
| `E2E (Playwright)`            | Only if listed individually | Skips until e2e specs exist (D6-08).                                                                |
| `Dependency audit (advisory)` | **No**                      | Non-blocking. See "Current audit findings".                                                         |
| `Detect changes`              | No                          | Helper job for path filters. Its result is part of `CI OK`.                                         |

### Why skipped jobs do not block

GitHub counts a **skipped** job as passing for a required check. Two mechanisms skip a job:

1. **Path filters.** On a pull request, a gate runs only when its paths changed (`Detect changes`). On `push`
   to `main`, every gate runs. A pull request that changes `.github/**` runs every gate.
2. **Missing target.** The job runs, prints a line starting with `SKIP:` and passes, until the thing it checks
   exists. Each gate activates by itself when its target appears. No workflow edit is needed.

| Gate                | Runs when                                                                                                            | Skips with `SKIP:` until                                                                                                                                   |
| ------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TypeScript          | `packages/**`, `apps/web/**`, `apps/browser-worker/**`, `apps/mock-marketplace/**`, root manifests; always on `main` | Never skips. Turbo runs only affected packages on PRs.                                                                                                     |
| TypeScript coverage | Inside `TypeScript`                                                                                                  | No target to wait for. Fails under 80% for `money`, `scoring`, `crypto-client` (see "Current gate status").                                                |
| Python              | `apps/orchestrator/**`, `apps/llm-stub/**`; always on `main`                                                         | No target to wait for.                                                                                                                                     |
| Python coverage     | Inside `Python`                                                                                                      | Skips per target until a non-`__init__.py` module exists in `src/apex/domain/`, `src/apex/signing/` or `src/apex/negotiation/guardrails*.py` (D3, D2, D5). |
| Integration tests   | Python paths; always on `main`                                                                                       | No test contains `mark.integration` in `apps/orchestrator/tests`.                                                                                          |
| Contracts drift     | `contracts/**`, `packages/shared-types/**`, generated contract code, TS paths; always on `main`                      | The root `package.json` has no `contracts:check` script (D2-01).                                                                                           |
| Migration drift     | `apps/web/prisma/**`, `apps/orchestrator/src/apex/db/**`; always on `main`                                           | `apps/web/prisma/migrations` does not exist (D2-03). The Postgres service only starts when this job runs.                                                  |
| E2E (Playwright)    | `apps/web/**`, `infra/**`, `compose.yaml`; always on `main`                                                          | No `*e2e*.spec.ts` file under `apps/web` (D6-08).                                                                                                          |
| Secret scan         | Always                                                                                                               | Never skips.                                                                                                                                               |
| LLM Portability     | Always                                                                                                               | Never skips.                                                                                                                                               |
| Dependency audit    | Always, advisory                                                                                                     | Never blocks (see below).                                                                                                                                  |

## Current gate status

Measured locally on the D1-04 branch. These are the facts a human needs before enabling enforcement.

- **TypeScript coverage is red today** (80% gate). Lines/statements: `@apex/money` 71.73%, `@apex/scoring`
  69.12%, `@apex/crypto-client` 30.99%. Branches are above 80% in all three. The packages belong to DEV-3
  (money, scoring) and DEV-2 (crypto-client). The gate was not lowered and no tests were added to those packages.
  Excluding the `index.ts` barrel files does not change the result.
- **Dependency audit** is advisory until the findings below are fixed.

## Current audit findings

Run locally with `pnpm audit --audit-level=high` (pnpm reports 31 findings: 9 high, 2 critical; the table below
lists the unique high and critical advisories, 8 high and 2 critical) and `pip-audit` against the locked environment
(3 findings, 2 packages). The job reports them without blocking. Fix owners are suggestions.

**pnpm (high and critical):**

| Severity | Package (path)                                                                           | Advisory                                                      | Fix available?                                                                                                        |
| -------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| critical | `tinypool` 1.1.1 (vitest 3.2.7)                                                          | Prototype pollution gadget leads to RCE in worker options     | Needs a vitest major bump (DEV-3…DEV-6 packages)                                                                      |
| high     | `vite` 5.4.21 (vitest 3.2.7)                                                             | launch-editor `fs.existsSync()` bypass on Windows             | Needs vite 6.4.4+, so a vitest major bump                                                                             |
| high     | `zod` 3.23.8 (bundled by `chromium-bidi` 0.11.0, via `puppeteer` 23 in `browser-worker`) | Memory exhaustion on oversized constrained collections        | Fixed only in zod 4.6.6+ for the `chromium-bidi` copy. Needs a puppeteer upgrade (DEV-5)                              |
| high     | `extract-zip` 2.0.1 (`browser-worker` via puppeteer)                                     | Symlink path traversal and arbitrary file writes              | No fixed version (DEV-5, via puppeteer 23)                                                                            |
| high     | `basic-ftp` 5.3.1 (`browser-worker` via puppeteer)                                       | Quadratic CPU denial of service in `Client.list()`            | Fixed in 6.2.1 (DEV-5, via puppeteer 23)                                                                              |
| high     | `deepmerge-ts` 7.1.5 (`apps/web` via prisma)                                             | Stack exhaustion on recursive objects                         | Fixed in 8.0.0 (DEV-2, needs a prisma update)                                                                         |
| high     | `postcss` 8.4.31 (bundled by `next` 15.5.29, `apps/web`)                                 | Source-map disclosure via `sourceMappingURL` (two advisories) | Fixed in 8.5.18. Needs a Next upgrade or a pnpm override (DEV-6). The workspace's own postcss 8.5.32 is not affected. |
| critical | `tinypool` (second advisory, same package)                                               | Prototype pollution gadget to RCE in `run()` options          | Same as above                                                                                                         |

**pip-audit (`apps/orchestrator`, locked):**

| Package             | Advisory                         | Finding                                                                                                                                                                                | Fix available?   |
| ------------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| `python-jose` 3.5.0 | PYSEC-2026-4298 / CVE-2026-85394 | Accepts DER-encoded public keys in HMAC initialization. Forged HS256 tokens can pass verification when algorithms are not restricted. **Relevant to D1-05 (JWT validation via JWKS).** | No fixed version |
| `ecdsa` 0.19.2      | PYSEC-2026-1325 / CVE-2024-23342 | Minerva timing attack on P-256 `sign_digest()`. The python-ecdsa maintainers do not fix it.                                                                                            | No fixed version |

pip-audit does not report severity. Check the severity of `python-jose` in the advisory before enforcing. Its
impact is high for JWT validation: **consider replacing `python-jose` with PyJWT** (pyproject is DEV-4's file,
auth is DEV-1's D1-05).

When a finding is fixed, remove it from this list. When the list is empty, make the two audit steps blocking by
removing `continue-on-error: true` from `.github/workflows/ci.yml` (the `dependency-audit` job) and add
`Dependency audit (advisory)` to the required list.

## Repository merge settings (available on the free plan)

These do not need a paid plan. Apply them now under **Settings → General**.

1. Section **Pull Requests**:
   - Uncheck **Allow merge commits**.
   - Uncheck **Allow rebase merging**.
   - Keep **Allow squash merging** checked.
   - Set the default squash commit message to **Default to pull request title**. The PR title carries the task ID (AGENTS.md 3.3).
   - Check **Automatically delete head branches**.
2. Click **Save** for each section if the page shows one.

Verify afterwards with the API (`GET /repos/<owner>/<repo>`): `allow_merge_commit=false`, `allow_rebase_merge=false`, `allow_squash_merge=true`, `delete_branch_on_merge=true`.

## Steps to apply the branch protection (once option A or B is in place)

1. Open the repository on GitHub, then **Settings → Rules → Rulesets → New ruleset → New branch ruleset**.
2. Name it `main protection`. Set **Enforcement status** to **Active**.
3. Under **Target branches**, add the pattern `main`.
4. Enable the rules listed in "Intended settings for `main`" above, with the values given there.
5. Under **Require status checks to pass**, add each check name from the list. Check names must match the job names exactly, and they appear only after the first successful run.
6. Under **Bypass list**, leave it empty unless the Tech Lead decides otherwise.
7. Click **Create**.
8. Open a test PR from a throwaway branch and confirm:
   - the CODEOWNERS reviewers are requested automatically,
   - merging is blocked until the required checks pass and one approval exists,
   - only squash merge is offered.
9. Close the test PR and delete its branch.

If the classic branch protection UI is used instead, the same settings live under **Settings → Branches → Add rule** with branch name pattern `main`.

## Verification commands

```bash
gh api repos/<owner>/<repo> --jq '{private, merge: .allow_merge_commit, rebase: .allow_rebase_merge, squash: .allow_squash_merge, auto_delete: .delete_branch_on_merge}'
gh api repos/<owner>/<repo>/rulesets        # 403 on the free plan for a private repo
gh api repos/<owner>/<repo>/branches/main/protection   # 403 on the free plan for a private repo
```

Replace `<owner>/<repo>` with the repository path. All three are read-only `GET` calls. The protection endpoint needs a token with admin access to the repository.
