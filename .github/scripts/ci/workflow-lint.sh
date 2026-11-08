#!/usr/bin/env bash
# Workflow lint (D1-04): actionlint on .github/workflows and shellcheck on every shell script under .github/scripts.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=tools.sh
source "$(dirname "${BASH_SOURCE[0]}")/tools.sh"

actionlint="$(ensure_tool actionlint)"
shellcheck="$(ensure_tool shellcheck)"
# actionlint runs shellcheck on `run:` blocks and looks it up on PATH.
PATH="$(dirname "${shellcheck}"):${PATH}"
export PATH

echo "actionlint $("${actionlint}" --version | sed -n '1p')"
"${actionlint}" .github/workflows/*.yml

echo "shellcheck $("${shellcheck}" --version | sed -n '2p')"
find .github/scripts -name '*.sh' -print0 | xargs -0 "${shellcheck}" --external-sources --source-path=SCRIPTDIR
echo "Workflow lint passed"
