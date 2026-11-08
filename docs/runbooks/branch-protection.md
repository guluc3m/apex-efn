# Branch protection for `main`

Owner: DEV-1. Task: D1-02 (governance) and D1-04 (required checks).

This runbook describes the settings we want on `main`, what can be applied today, and how to apply the rest.

## Current limitations (verified)

These facts were checked against the GitHub API on the repository itself:

1. The repository is **private** and the organisation is on the **free plan**.
2. Branch protection and repository rulesets return **403** with "Upgrade to GitHub Pro or make this repository public". The `main` branch cannot be protected today.
3. CODEOWNERS is only **enforced** (review required, reviews auto-requested) on private repositories with GitHub Pro, Team or Enterprise, or on public repositories. The file `.github/CODEOWNERS` is in place, but on this plan it does not request reviews or block merges.
4. GitHub Actions is **disabled for this repository by organisation policy**. The CI jobs in `.github/workflows/ci.yml` do not run, so no required status check can report a result.

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
  - Required checks today (job names from `.github/workflows/ci.yml`):
    - `TypeScript`
    - `Python`
    - `Security`
    - `LLM Portability Check`
  - D1-04 extends this list (coverage gates, contract drift, migration drift, E2E). Update this section when it does.
- Require linear history: **on** (squash merges only produce linear history).
- Block force pushes: **on**.
- Block deletion of `main`: **on**.
- Bypass list: empty. Any exception is a decision for the Tech Lead and must be recorded in an issue.

## Repository merge settings (available on the free plan)

These do not need a paid plan. Apply them now under **Settings → General**.

1. Section **Pull Requests**:
   - Uncheck **Allow merge commits**.
   - Uncheck **Allow rebase merging**.
   - Keep **Allow squash merging** checked.
   - Set the default squash commit message to **Default to pull request title**. The PR title carries the task ID (AGENTS.md 3.3).
   - Check **Automatically delete head branches**.
2. Click **Save** for each section if the page shows one.

Verify afterwards with the API: `merge_commit_allowed=false`, `rebase_merge_allowed=false`, `squash_merge_allowed=true`, `delete_branch_on_merge=true`.

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

Replace `<owner>/<repo>` with the repository path. Do not run these with a token that has write permissions.
