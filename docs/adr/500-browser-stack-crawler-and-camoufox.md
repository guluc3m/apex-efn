# ADR-500: Browser stack: deterministic crawler for reading, Playwright for interaction, shared Camoufox

## Status

Proposed (DEV-5). Needs TL review: licence (AGPL-3.0) and a deviation from the spec's Puppeteer wording.

## Context

The team asked DEV-5 to split browser work in two:

- **Reading** (search, product, seller profile, reviews): a deterministic crawler such as crw or Firecrawl.
- **Interaction** (seller chat, login): Puppeteer or WebMCP.
- Both should use one shared instance of [Camoufox](https://github.com/daijro/camoufox), an anti-detect
  Firefox build, since both tools support Firefox.

Spec 5.4 asks for Puppeteer with `puppeteer-extra` stealth, Playwright as an alternative per adapter, and
`transport: http | browser` with the browser only where JS, login or chat require it.

Findings (checked 2026-11-08):

- **Camoufox is driven by Playwright over Juggler**, not CDP. Puppeteer/WebDriver BiDi support is "not
  planned" by the maintainer (camoufox issue #103, closed July 2026). Puppeteer would need a third-party
  CDP-to-Juggler bridge with unverified claims. Camoufox has a server mode (`camoufox server` /
  `launchServer`) that exposes a Playwright websocket, so many clients can share one instance with
  `firefox.connect(wsEndpoint)`. It is marked experimental. One server is one browser, so the fingerprint
  does not rotate between contexts. Client and server Playwright versions must match (major.minor).
- **WebMCP** (`document.modelContext`) is a W3C Community Group draft. It runs in Chromium behind an origin
  trial or flag, has no Firefox implementation, and only works on sites that register tools themselves.
  It cannot run on Camoufox and is useless on third-party marketplaces.
- **crw** (fastcrw/crw, Rust, AGPL-3.0) is a single container with a Firecrawl-compatible API
  (`/v1/scrape`, `/v1/crawl`, `/v1/map`). It respects robots.txt by default and needs no LLM for
  markdown/HTML/links output. It renders JS through CDP renderers, or reaches Camoufox only through its own
  REST sidecar (`camofox-browser`), not through a shared Playwright websocket.
- **Firecrawl self-hosted** (AGPL-3.0) needs about six services, and its `playwright-service` is hardcoded to
  Chromium.

## Decision

1. **Interaction uses Playwright (`playwright-core`) connected to a shared Camoufox server.** Puppeteer
   and WebMCP are not used. This is the "Playwright as an alternative" path the spec already allows. Each
   job gets its own browser context (cookies, storage, proxy) on the shared instance.
2. **Reading uses crw** behind the browser worker. Adapters call crw's `/v1/scrape` (formats `html` /
   `markdown` / `links`) and parse the result with deterministic code (selectors and regexes, no LLM).
   JSON APIs (official APIs, `mock-a`) are read with plain HTTP (`undici`). Rendering is off by default
   (`renderJs: false`). It is turned on per adapter only when a page needs JS, using the Camoufox path that
   a spike (D5-02) proves out.
3. **One Camoufox instance per environment**, run as a container with a pinned Camoufox and Playwright
   version. The browser worker depends on `playwright-core` with the same major.minor. The instance is a
   pool with context limits, recycling and a watchdog (D5-02). Session state per account stays encrypted
   in Vault (D1-06), and credentials never leave the worker.
4. **The mock marketplace is shaped for this split.** `mock-b` serves fully server-rendered HTML (crawlable
   without a browser) plus a chat driven by plain HTML forms (Playwright). `mock-a` is a JSON API (HTTP).

## Consequences

- `puppeteer`, `puppeteer-extra` and `puppeteer-extra-plugin-stealth` become unused in the browser worker and
  can be removed in D5-02. Stealth comes from Camoufox's fingerprinting, not from a plugin.
- **Licence:** crw's engine is AGPL-3.0. Running it unmodified as a separate service and calling its HTTP
  API is the intended use, but the TL must confirm this is acceptable. Alternative if not: a small in-house
  fetcher (`undici` + HTML parser) in the worker, which keeps the same adapter interface.
- **Camoufox risks:** a single maintainer with a long release gap in 2025-2026; server mode is
  experimental; breakage when Playwright versions drift; known container hangs on some builds. Mitigation:
  pin versions, add a health check plus restart, and keep adapters working on `transport: http` when the
  browser is down.
- No fingerprint rotation per context on a shared server. If a platform needs it, run more than one
  instance (one per platform or per proxy).
- Compose and Dockerfiles (owned by DEV-1) need a `camoufox` service and a `crw` service. Requested
  through a `platform-request` issue.
- Spec 5.4 says "Puppeteer". This ADR records why interaction uses Playwright instead. The product
  behaviour does not change.

## Related

- PROMPT-IMPLEMENTACION.md 5.4, 5.9, 5.11
- AGENTS.md D5-01, D5-02, D5-03, D5-04, D5-06
- docs/compliance/mock-marketplace.md
- https://github.com/daijro/camoufox/issues/103
- https://camoufox.com/python/remote-server/
- https://github.com/fastcrw/crw
- https://github.com/webmachinelearning/webmcp
