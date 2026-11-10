# Local CI (`pnpm ci:local`)

Owner: DEV-1. Task: D1-04.

`pnpm ci:local` runs every job of `.github/workflows/ci.yml` on your machine, in CI order, with the scope CI
uses on `main`, and prints one summary table. Run it before you open or merge a PR. The merge gate is a passing
full CI: the local run now, and the `CI OK` check on GitHub once Actions is enabled (see
`docs/runbooks/branch-protection.md`).

## What it runs

| Job                | Script                   | What it checks                                                                                                                                          | Result when not applicable                                                      |
| ------------------ | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `workflow-lint`    | `ci/workflow-lint.sh`    | actionlint on `.github/workflows/*.yml`, shellcheck on `.github/scripts/**/*.sh`                                                                        | never skips                                                                     |
| `typescript`       | `ci/typescript.sh`       | `turbo run build lint typecheck test` (full), then the coverage ratchet for `money`, `scoring`, `crypto-client`                                         | never skips                                                                     |
| `python`           | `ci/python.sh`           | `ruff check`, `mypy src/`, unit tests with the 80% coverage gate for every target that exists                                                           | never skips (coverage gate per target)                                          |
| `integration`      | `ci/integration.sh`      | Phase A: real Vault (no Docker), `pytest -m vault_integration` and the browser-worker real-Vault test. Phase B: Testcontainers, `pytest -m integration` | Each phase `SKIP`s until its target exists. Phase B needs Docker once it exists |
| `secret-scan`      | `ci/secret-scan.sh`      | TruffleHog 3.99.8, verified secrets only, on the commits this branch adds                                                                               | never skips                                                                     |
| `dependency-audit` | `ci/dependency-audit.sh` | `pnpm audit --audit-level=high` and `pip-audit` on the locked Python environment                                                                        | advisory: findings are printed, the job still passes                            |
| `llm-portability`  | `ci/llm-portability.sh`  | Criterion 25: no proprietary LLM endpoints or vendor SDK imports (self-test first)                                                                      | never skips                                                                     |
| `contracts-drift`  | `ci/contracts-drift.sh`  | root script `contracts:check` (D2-01)                                                                                                                   | `SKIP` until the script exists                                                  |
| `migration-drift`  | `ci/migration-drift.sh`  | `prisma migrate diff` from migrations to the schema (D2-03)                                                                                             | `SKIP` until `apps/web/prisma/migrations` exists; then Docker is required       |
| `e2e`              | `ci/e2e.sh`              | Playwright on the compose stack (D6-08)                                                                                                                 | `SKIP` until an e2e spec exists under `apps/web`; then Docker is required       |

Results:

- `PASS`: the script exited 0.
- `SKIP`: the script exited 0 and printed a `SKIP:` line with the reason. The reason is shown in the summary.
- `FAIL`: the script exited non-zero. Its log path is shown in the summary.
- `NOT RUN`: `--fail-fast` stopped the run before this job.

A job that needs Docker and finds the target present but no Docker running **fails** with
`requires Docker`. It never passes silently.

## Prerequisites

- Node 22 (`.nvmrc`) and pnpm 9 (see `packageManager` in `package.json`).
- uv `0.13.7` (the version CI pins; see `UV_VERSION` in `ci.yml`).
- Dependencies installed:
  ```bash
  pnpm install --frozen-lockfile
  (cd apps/orchestrator && uv sync --locked --dev)
  ```
- Network access for the first run: `git fetch origin` (the runner tries it and continues offline), the pinned
  security tools (downloaded once, see below), `pnpm audit`, and `pip-audit`.
- Docker: **only** for `migration-drift`, `e2e`, and phase B (Testcontainers) of `integration`, and only once their
  targets exist. Phase A of `integration` (real Vault) needs no Docker.

#### The `integration` job

`ci/integration.sh` runs three phases. Each phase skips with its own reason when its target does not exist:

- **Phase A, Vault (no Docker).** Target: a test marked `vault_integration` under `apps/orchestrator/tests`, or the
  real-Vault block in `apps/browser-worker/src` (gated by `VAULT_INTEGRATION_ADDR`). The script downloads the pinned
  Vault 1.21.4 binary (`tools.sh`, SHA-256 checked), starts `vault server -dev` on a free local port (it also needs
  port+1 free for the cluster address), bootstraps it with `infra/vault/init.sh`, runs both test sets against it,
  and stops it. The stop sends SIGTERM and, after 10 s, SIGKILL.
- **Phase B, Testcontainers (Docker).** Target: a test marked `integration`. Without Docker this phase **fails**
  with `requires Docker`.
- **Phase C, adversarial negotiation (D5-09, no Docker).** Target: `apps/orchestrator/tests/negotiation/adversarial`.
  It boots the mock marketplace with `tsx`, so it needs Node and `pnpm install`. It runs with
  `APEX_REQUIRE_MOCK_MARKETPLACE=1`, which turns a missing Node or mock into a **failure** instead of a skip, so
  the suite cannot silently disappear from CI.

The job result: `FAIL` if any phase fails. `PASS` if at least one phase ran and none failed (the message says which
phases ran). `SKIP` only if all phases skip. Markers:

| Marker              | Meaning                                                                                                                  | Excluded from the unit run (`ci/python.sh`) |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| `integration`       | Testcontainers, needs Docker                                                                                             | yes                                         |
| `vault_integration` | Real Vault dev server (pinned), no Docker. Self-skips without `VAULT_INTEGRATION_ADDR`, so plain `pytest` stays hermetic | yes                                         |

### Pinned security tools

`secret-scan`, `workflow-lint`, `integration` (phase A) and `.github/scripts/ci/tools.sh` need these binaries at the
versions pinned in `tools.sh`: TruffleHog 3.99.8, actionlint 1.7.12, shellcheck 0.11.0, Vault 1.21.4.

- A binary on your `PATH` is used only if it reports exactly the pinned version.
- Otherwise the tool is downloaded into `${XDG_CACHE_HOME:-$HOME/.cache}/apex-ci-tools/<tool>-<version>/`,
  outside the repository.
- Every download is checked against the SHA-256 pinned in `tools.sh` before anything is unpacked. A mismatch
  stops the run.
- Vault ships as a `.zip`. It is unpacked with the first tool found: `unzip`, `bsdtar`, `python3`, or `uv run python`.
- A cached binary is checked against the hash recorded when it was installed. If that fails, the cached copy is
  discarded and downloaded again.

## Usage

```bash
pnpm ci:local                                  # every job, keep going, summary at the end
bash .github/scripts/ci-local.sh --list         # job names and what they do
bash .github/scripts/ci-local.sh --job python --job secret-scan   # selected jobs only (repeatable)
bash .github/scripts/ci-local.sh --fail-fast    # stop after the first FAIL
bash .github/scripts/ci-local.sh --no-fetch     # do not run git fetch origin first
```

The exit code is non-zero if any job failed. Logs go to `${TMPDIR:-/tmp}/apex-ci-local.XXXXXX/<job>.log`, and the
path is printed at the end.

Each job can also run alone: `bash .github/scripts/ci/<job>.sh`.

### Scope

- Locally, `typescript` runs the full scope (as on `main`), not only the packages changed against `origin/main`.
- Locally, `secret-scan` scans the commits that HEAD adds on top of `merge-base(origin/main, HEAD)`. On `main`
  itself that range is empty. If `origin/main` does not exist, it scans the whole history.
- On a pull request, CI runs `typescript` in affected-only mode (`CI_TS_SCOPE=affected`).

## Coverage ratchet

`.github/coverage-baseline.json` holds the current TypeScript coverage (rounded down to 2 decimals) for `@apex/money`,
`@apex/scoring` and `@apex/crypto-client`. `typescript` compares the measured values with it:

- A metric may not drop more than 0.01 below its baseline.
- Baselines only go up. The check fails if the working copy is lower than `origin/main`'s baseline, or if an entry
  that main has is removed while its package is below 80%.
- A package whose four metrics are all at least 80% is held to the hard 80% gate. A package with no baseline
  entry is held to it too.
- When a metric rises above its baseline, the output prints `hint: ... raise baseline to X`. That does not fail.
- **Graduation is mandatory.** The moment all four metrics reach 80% while the baseline is still lower, the check
  fails until you run `--update-baseline` and commit the file. Without this, a package could reach 85%, keep its old
  baseline of 71%, and later fall back to 75% unnoticed. After graduation the hard 80% gate applies for good.

The baseline file lives under `.github/`, which belongs to DEV-1, but any lane may commit a **raise** to it in the same
PR as the tests that earned it. Lowering a value is never allowed (second rule above).

Raise the baseline after you add tests:

```bash
node .github/scripts/ci/ts-coverage.mjs --update-baseline
```

The flag writes the maximum of the working copy, `origin/main` and the measured value. It never lowers a value. It
does not write the file if any test fails. Commit the changed `.github/coverage-baseline.json` with the tests.

Python has no baseline. The 80% gate applies to each target (`apex.domain`, `apex.signing`,
`apex.negotiation` guardrails) once a real module exists for it. Empty `__init__.py` files do not count.

## How CI and local share scripts

Every job in `.github/workflows/ci.yml` calls `bash .github/scripts/ci/<job>.sh`. The YAML only does what needs the
GitHub runner: checkout, toolchain setup (pnpm, Node, uv, Python), service containers, artifact upload, and the
`CI OK` aggregate. Everything that decides pass, fail or skip is in the script, so `ci:local` runs the same logic.

Known differences, all in the environment rather than the checks:

- Services: CI starts the shadow Postgres for `migration-drift` as a job service. Locally the script starts a
  throwaway pgvector container, unless you export `SHADOW_DATABASE_URL`.
- `playwright install --with-deps` runs only when `CI=true` (it needs root).
- `CI_TS_SCOPE` and `CI_BASE_REF` differ, as described in "Scope".
- Secret scanning in CI uses the PR base or the push `before` commit (`CI_BASE_SHA`).

## Troubleshooting

- **`SHA-256 mismatch`** when a tool is downloaded: the download is corrupt or was changed upstream. Do not
  bypass it. Retry once. If it still fails, check the release on GitHub before you change the pinned hash in
  `tools.sh`.
- **`requires Docker`**: start Docker Desktop or the Docker daemon, then rerun the job. The message appears only
  once the job's target exists.
- **`TypeScript coverage ratchet` fails with "baseline lowered"**: your branch has a lower value than `origin/main`.
  Restore the value. Do not edit the file to lower it.
- **`coverage ... is below baseline`**: a test was removed or a file added without tests. Add tests. If the drop is
  intended, the decision belongs to the owner of the package, recorded in an issue.
- **`turbo` says `@apex/web#typecheck` failed** while `next build` runs: this was a race. It is fixed by a
  dependency in `turbo.json` (`@apex/web#typecheck` depends on `@apex/web#build`). Run `pnpm exec turbo run build typecheck --force`
  to confirm.
- **`secret-scan` reports a secret**: rotate it first. Remove it from the history with the owner's approval.
  Adding an allowlist entry needs a review from the Tech Lead.
- **`git fetch origin` failed**: the runner continues with the local `origin/main`. Results may be stale. Rerun with
  network access before a merge.
- **`dependency-audit` reports findings**: advisory. They are listed in `docs/runbooks/branch-protection.md`
  ("Current audit findings"). The job still passes.
