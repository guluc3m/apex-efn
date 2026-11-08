#!/usr/bin/env bash
# Secret scan (D1-04): TruffleHog, verified secrets only, pinned version (tools.sh).
# Range to scan:
#   CI (GITHUB_ACTIONS=true): CI_BASE_SHA, the PR base or the push "before" commit. Empty or all zeros
#     (first push of a branch) means the whole history.
#   Local: commits that HEAD adds on top of merge-base(origin/main, HEAD). No origin/main means the whole history.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=tools.sh
source "$(dirname "${BASH_SOURCE[0]}")/tools.sh"

ZEROS=0000000000000000000000000000000000000000
base=""
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  base="${CI_BASE_SHA:-}"
  if [ "${base}" = "${ZEROS}" ] || [ -z "${base}" ]; then
    echo "No base commit: scanning the whole history"
    base=""
  fi
else
  if git rev-parse --verify --quiet origin/main >/dev/null; then
    base="$(git merge-base origin/main HEAD)"
  else
    echo "NOTE: origin/main not found; scanning the whole history"
  fi
fi

trufflehog="$(ensure_tool trufflehog)"
args=(git file://. --branch HEAD --only-verified --fail --no-update)
if [ -n "${base}" ]; then
  echo "Scanning ${base}..HEAD (verified secrets only)"
  args+=(--since-commit "${base}")
else
  echo "Scanning the whole history (verified secrets only)"
fi
"${trufflehog}" "${args[@]}"
echo "No verified secrets found"
