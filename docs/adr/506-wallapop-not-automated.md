# ADR-506: Wallapop is not automated

## Status

Accepted (DEV-5, D5-11). This is a compliance decision, not a technical one; it can be revisited only with written
consent from Wallapop.

## Context

The owner chose Wallapop as the first real marketplace for D5-11 (autonomous sending on one real platform, plus
the third and fourth adapters). The lane's own rules (AGENTS.md D5-06 step 1 and D5-11) say a platform whose terms
forbid automation is documented and not scraped.

What we verified on 2026-11-11:

- **The terms forbid it.** Wallapop's *Términos y Condiciones*, clause 3.1.2: point 15 prohibits systematic
  extraction or reuse of platform content without express written consent, naming search robots and data mining;
  point 17 prohibits external software tools (bots) unless authorised; point 18 limits use to personal purposes
  unless the account is a Professional User.
- **`robots.txt` forbids the entry points.** `User-agent: *` disallows `/search` and `/*?` — discovery is exactly
  a search query — plus `/login`, `/register`, `/auth/` and `/app/`, which is where a session would be opened.
- **There is no public search API.** API Connect is for professional sellers to manage their own listings; it
  does not expose other sellers' catalogues.

Full analysis: `docs/compliance/wallapop.md`.

## Decision

**No Wallapop adapter is written, and nothing in the codebase special-cases Wallapop.** The registry keeps it
unregistered; `platform.wallapop.enabled` stays off; `negotiation.autonomous_send` stays inert because it has no
authorised platform to send on.

This is not a limitation we can engineer around. The prohibition is on the activity, not the technique: a
different transport, a proxy or a residential session changes how the request is made, not whether it is allowed.
The polite client already refuses disallowed URLs (`robots_disallowed`), which is the behaviour we want.

Additionally, the worker's **User-Agent policy** is now enforced in configuration (see below): it must be an
anonymous product token plus an organisational URL and may not contain an email, a credential, a tenant or an
account identifier. It is identical for every tenant, so a platform cannot link a request to one of our customers.

## Alternatives, in order

1. **Ask for written consent.** The clause itself offers that route; a partner agreement may come with an API.
2. **Use an official API if one appears** for catalogue/supplier search (today API Connect does not offer it).
3. **Target a platform that allows it** — a B2B wholesale marketplace with a public API. The adapter interface,
   the fixture harness, the contract suite and the browser pool are platform-agnostic, so this is a plugin plus a
   compliance doc.

## Consequences

- D5-11's "one real platform" cannot be Wallapop. The autonomous flag, the webhooks and the third/fourth adapter
  slots stay ready; the platform slot is empty.
- A mission that targets Wallapop must fail closed with a clear message (`platform_disabled` or a configuration
  error at onboarding), never with a best-effort scrape.
- Future adapters inherit the User-Agent guard; setting a personal or tenant-identifying UA makes the worker
  refuse to start, which is the loud failure we want.

## Related

- `docs/compliance/wallapop.md` (terms and robots citations), ADR-500, ADR-505, ADR-900 (Q10).
- Issues #70 (D5-11), #65 (adapter rules), #130 (DEV-1 services).
