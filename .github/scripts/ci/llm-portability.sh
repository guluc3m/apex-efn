#!/usr/bin/env bash
# Criterion 25 (D1-04): no proprietary LLM endpoints or vendor SDK imports. The rules live in
# .github/scripts/llm-portability.sh, which also self-tests its deny-list first.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

bash .github/scripts/llm-portability.sh --self-test
bash .github/scripts/llm-portability.sh
