#!/usr/bin/env bash
# Criterion 25 (PROMPT-IMPLEMENTACION.md §9): the LLM access path must stay
# OpenAI-compatible (/v1/chat/completions) so that self-hosted engines work.
#
# Usage:
#   .github/scripts/llm-portability.sh              scan the repository, exit 1 on any hit
#   .github/scripts/llm-portability.sh --self-test  prove the deny-list catches known-bad samples
#                                                   and ignores a known-good one
set -euo pipefail

# Each rule: "<group>|<extended regex>". Matched case-sensitively.
RULES=(
  "endpoint|/v1/(assistants|threads|batches|vector_stores|responses)([^A-Za-z0-9_]|$)"
  "sdk-method|(assistants\.create|beta\.assistants|beta\.threads|batches\.create)"
  "vendor-host|api\.anthropic\.com|generativelanguage\.googleapis\.com"
  "js-vendor-import|(from|require\(|import\()[[:space:]]*['\"](openai|@anthropic-ai/sdk|@google/generative-ai|@mistralai/[^'\"]*|cohere-ai)(/[^'\"]*)?['\"]"
  "py-vendor-import|^[[:space:]]*(import|from)[[:space:]]+(openai|anthropic|google\.generativeai|cohere|mistralai|langchain_openai|langchain_anthropic)([^A-Za-z0-9_]|$)"
)

# Prints "<group>\t<file>:<line>\t<text>" for every hit under the given root.
scan() {
  local root="$1" rule group pattern
  for rule in "${RULES[@]}"; do
    group="${rule%%|*}"
    pattern="${rule#*|}"
    grep -rnIE \
      --include='*.ts' --include='*.tsx' --include='*.js' --include='*.mjs' --include='*.cjs' --include='*.py' \
      --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=dist --exclude-dir=.next \
      --exclude-dir=.git --exclude-dir=.turbo --exclude-dir=docs \
      -e "$pattern" "$root" 2>/dev/null \
      | grep -vE "^${root%/}/(\.github/workflows/|\.github/scripts/llm-portability\.sh)" \
      | sed -E "s/^/${group}\t/" || true
  done
}

self_test() {
  local tmp failures=0 name expect file content hits
  tmp="$(mktemp -d)"
  # Expand $tmp now: it is local to this function and gone when EXIT fires.
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" EXIT

  # name | expected group ("ok" = must not be caught) | file | content
  local CASES=(
    "endpoint-threads|endpoint|a.ts|await fetch(base + '/v1/threads', { method: 'POST' })"
    "endpoint-batches|endpoint|a.py|httpx.post(f\"{base}/v1/batches\")"
    "endpoint-responses|endpoint|a.ts|const url = \`\${base}/v1/responses\`"
    "sdk-assistants|sdk-method|a.ts|await client.assistants.create({ model: 'x' })"
    "sdk-beta-threads|sdk-method|a.py|client.beta.threads.create()"
    "host-anthropic|vendor-host|a.ts|const url = 'https://api.anthropic.com/v1/messages'"
    "host-gemini|vendor-host|a.js|fetch('https://generativelanguage.googleapis.com/v1beta')"
    "js-openai-from|js-vendor-import|a.ts|import OpenAI from 'openai';"
    "js-openai-dq|js-vendor-import|a.tsx|import { OpenAI } from \"openai\";"
    "js-openai-require|js-vendor-import|a.cjs|const o = require('openai');"
    "js-anthropic-sdk|js-vendor-import|a.mjs|import Anthropic from '@anthropic-ai/sdk';"
    "js-gemini-sdk|js-vendor-import|a.js|import { GoogleGenerativeAI } from '@google/generative-ai';"
    "js-mistral|js-vendor-import|a.ts|import MistralClient from '@mistralai/mistralai';"
    "js-cohere|js-vendor-import|a.js|const c = require('cohere-ai');"
    "py-openai|py-vendor-import|a.py|import openai"
    "py-openai-from|py-vendor-import|a.py|from openai import OpenAI"
    "py-anthropic|py-vendor-import|a.py|  import anthropic"
    "py-gemini|py-vendor-import|a.py|from google.generativeai import GenerativeModel"
    "py-langchain-openai|py-vendor-import|a.py|from langchain_openai import ChatOpenAI"
    "py-langchain-anthropic|py-vendor-import|a.py|import langchain_anthropic"
    "ok-httpx-chat|ok|a.py|resp = httpx.post(f\"{base_url}/v1/chat/completions\", json=body)"
    "ok-openai-compat-name|ok|a.py|from trato.llm.openai_compat import chat"
    "ok-threads-word|ok|a.ts|const threadsCount = 3; // threads of discussion"
  )

  local case
  for case in "${CASES[@]}"; do
    IFS='|' read -r name expect file content <<<"$case"
    local dir="$tmp/$name"
    mkdir -p "$dir"
    printf '%s\n' "$content" >"$dir/$file"
    hits="$(scan "$dir")"
    if [ "$expect" = "ok" ]; then
      if [ -n "$hits" ]; then
        echo "FAIL $name: known-good sample was flagged:"
        echo "$hits"
        failures=$((failures + 1))
      else
        echo "ok   $name: not flagged"
      fi
    else
      if printf '%s\n' "$hits" | grep -q "^${expect}"; then
        echo "ok   $name: flagged by [$expect]"
      else
        echo "FAIL $name: expected group [$expect], got: ${hits:-no hits}"
        failures=$((failures + 1))
      fi
    fi
  done

  if [ "$failures" -gt 0 ]; then
    echo "self-test FAILED: $failures case(s)"
    exit 1
  fi
  echo "self-test passed: ${#CASES[@]} cases"
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit 0
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
hits="$(cd "$ROOT" && scan .)"

if [ -n "$hits" ]; then
  echo "ERROR: proprietary LLM access detected. Use only OpenAI-compatible /v1/chat/completions."
  printf '%s\n' "$hits" | awk -F'\t' '{ printf "  [%s] %s  %s\n", $1, $2, $3 }'
  exit 1
fi
echo "OK: no proprietary LLM endpoints or vendor SDK imports found"
