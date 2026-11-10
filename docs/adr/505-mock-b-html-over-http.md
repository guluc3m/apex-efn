# ADR-505: `mock-b` reads HTML over the polite HTTP client

## Status

Proposed (DEV-5, D5-06). `TL approval: yes` (D5-06 is in the TL-gated list).

## Context

ADR-500 chose the production browser stack: `crw` for crawling and Camoufox (via Playwright) for anything that
only exists in a rendered DOM, with chat driven through the browser. D5-06 asks for the `mock-b` adapter "HTML via
crw, chat via Playwright on Camoufox".

Two facts decide this ADR:

1. `mock-b` is the **mock marketplace** (`apps/mock-marketplace`): a local Fastify app that serves plain HTML with
   `data-testid` hooks and chat as ordinary form posts. There is nothing to render that the HTML does not already
   contain, no login, no session, no anti-bot surface.
2. `crw` and Camoufox are DEV-1 services that do not exist yet (#130). Making the mock adapter depend on them
   would leave D5-06 blocked on infrastructure it does not need.

## Decision

**The `mock-b` adapter reads the site over the polite HTTP client and parses the HTML.** It declares
`transport: http`.

- Fetching, spacing, retries, `robots.txt`, backoff and the closed error mapping are the ones every adapter
  already uses (`PoliteHttpClient`), so the mock exercises the same path a crawler does.
- Parsing is isolated in `adapters/mock-b/mapping.ts` behind `html.ts`. A missing `data-testid` answers
  `dom_changed` naming only the selector — never page content — which is the runbook already written in D5-10.
- Chat is driven as the page drives it: `POST /mock-b/chat`, then `POST /mock-b/chat/{id}/send`, reading the
  thread from the page. The adapter's `ChatAdapter` port is unchanged, so a browser-backed transport can replace
  it for a real platform without touching the worker.
- `screenshot()` answers `upstream_error` ("no rendered chat without a browser") instead of pretending.

**Camoufox stays the rule for real platforms (D5-11).** When a platform needs a rendered DOM, a login or
anti-bot handling, the adapter uses the browser pool (D5-02) behind the same `PlatformAdapter` interface; nothing
in the orchestrator changes. `crw`, when DEV-1 delivers it, becomes an `HttpTransport` implementation — the
adapter's parsing does not change either.

## Consequences

- D5-06 is testable in the `typescript` CI job with recorded HTML fixtures and the shared adapter contract suite;
  no browser binary or external service is needed to merge it.
- The parser is the part most likely to break on a real platform, so it is behind `mapping.ts` with explicit
  `dom_changed` failures and fixtures that mirror the live pages.
- The deviation is visible and reversible: switching `mock-b` to the browser stack is a transport change plus a
  different fetch/parse path, not a rewrite of the adapter's behaviour.
- The mock's chat has no session or anti-bot behaviour, so this ADR does **not** validate the session, proxy or
  takeover paths against a real platform; D5-11 does that.

## Related

- ADR-500 (browser stack), ADR-501 (guardrails), ADR-504 (controls), ADR-900 (Q10: `mock-a`/`mock-b` in Phase 1).
- `docs/compliance/mock-marketplace.md`; issue #65, #130.
