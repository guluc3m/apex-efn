# Compliance: Wallapop (target platform for D5-11)

| Field | Value |
|---|---|
| Platform | Wallapop (`wallapop.com`, `es.wallapop.com`) |
| Owner lane | DEV-5 (Browser Automation & Negotiation) |
| Status | **Not implemented: automation is forbidden by the platform's terms.** |
| Approved by | Pending: written consent from Wallapop, or a signed partnership/API agreement |
| Last reviewed | 2026-11-11 |

## 1. What the platform's terms say

Wallapop's *Términos y Condiciones* (revision of 10 April 2026, `about.wallapop.com/condiciones-de-uso`),
clause 3.1.2, which lists what a user must not do:

> **15.** No extraer de forma sistemática ni reutilizar parte o todo del contenido de la Plataforma, sin nuestro
> expreso consentimiento por escrito. En particular, no se permite (i) el uso de herramientas o robots de
> búsqueda, ni (ii) la extracción de datos (ya sea en una o varias ocasiones o de forma masiva -minería de
> datos-).
>
> **17.** No utilizar herramientas de software externas (bots, etc.), salvo que dicho uso sea autorizado o
> permitido por nosotros.
>
> **18.** Excepto en el caso de que te identifiques como Usuario Profesional, utilizar nuestros Servicios
> únicamente para tu beneficio personal y no con fines comerciales.

Read together: automated search, systematic extraction and external bots are prohibited **without express written
consent**, and use is personal-only unless the account is a Professional User. APEX-EFN is a commercial,
multi-tenant sourcing product; it is neither personal use nor a consent-holding professional account.

## 2. What `robots.txt` says

The current `https://wallapop.com/robots.txt` applies to `User-agent: *`:

```
User-agent: *
Allow: /
Disallow: /wallapay
Disallow: /faq
Disallow: /rules
Disallow: /safety
Disallow: /toc$
Disallow: /priv
Disallow: /cookies
Disallow: /register
Disallow: /login
Disallow: /auth/
Disallow: /app/
Disallow: /search
Disallow: /*?
```

Two consequences, independent of the terms:

1. **`/search` is disallowed**, and so is **any URL carrying a query string** (`/*?`). Discovery — the entry point
   of every mission — is exactly that.
2. `/login`, `/register`, `/auth/` and `/app/` are disallowed, so the assisted session flow that D5-02 built has
   nothing it may legally touch either.

Our own polite client enforces this and would answer `robots_disallowed` before a request left the worker. That
is the intended behaviour, not an obstacle to work around.

## 3. Is there an API?

Wallapop's official **API Connect** is for professional sellers: publishing their own items and managing their
sales. Its documented surface does not include searching or reading other sellers' listings. There is no public,
documented search API.

Community libraries and third-party scraping services that read Wallapop listings exist. They rely on
undocumented endpoints or rendered pages and are subject to the same terms; using them would be the same
violation with an extra intermediary.

## 4. Decision

**The Wallapop adapter is not implemented.** Per the lane's own rule (AGENTS.md D5-06 step 1, D5-11) a platform
whose terms forbid automation is documented, not scraped. There is no code to write that makes this compliant:
the prohibition is on the activity, not on the technique.

Consequences:

- No `wallapop` adapter is registered in `AdapterRegistry`; the flag `platform.wallapop.enabled` stays off.
- The autonomous-send flag (`negotiation.autonomous_send`) remains inert, because it needs a real platform with an
  authorised adapter.
- Nothing in DEV-5's merged code special-cases Wallapop; the mock adapters and the mock marketplace remain the
  only wired platforms.

## 5. What would make it possible

In order of preference:

1. **Written consent / partnership** — Wallapop's own clause allows extraction with "expreso consentimiento por
   escrito". A signed agreement (or an affiliate/partner programme that permits catalogue access) is the only
   clean route, and it may come with an API of its own.
2. **Official API Connect**, if it ever exposes a supplier/catalogue search for professional accounts. Today it
   does not.
3. **A different platform** whose terms allow it, or that offers a public API (e.g. a B2B wholesale marketplace).
   The adapter interface, fixture harness and contract suite are already in place, so switching target is a
   plugin plus a compliance doc, not a redesign.

Until one of those exists, the answer for a mission that targets Wallapop is to fail closed with a clear message,
not to attempt a request.

## 6. User-Agent policy (applies to every adapter)

The worker identifies itself honestly and **anonymously**:

- The User-Agent is a product token plus an organisational contact URL: `APEX-EFN-bot/<version> (+https://…)`.
- It **never** contains a person's name, email, user id, tenant id, account id, API token or any other
  identifier. This is enforced in `loadConfig`: a User-Agent with `@` or with a credential/identity word
  (`token`, `secret`, `tenant`, `account`, `password`, `apikey`) is rejected before the worker starts.
- It is the same for every tenant: the platform must not be able to link a request to a customer of ours.
- Requests carry no tenant, mission, account or trace identifiers in headers; those stay inside the worker and
  in our telemetry.

The reason is not cosmetic: a User-Agent is sent in clear text to every platform and ends up in their logs. An
identifier there is a leak of the customer's or the operator's identity to a third party, and it is the exact
class of bug other tools have shipped.

## 7. References

- Wallapop *Términos y Condiciones*: `about.wallapop.com/condiciones-de-uso` (clause 3.1.2, points 15, 17, 18).
- `https://wallapop.com/robots.txt` (checked 2026-11-11).
- ADR-500 (browser stack), ADR-505 (how adapters read HTML), ADR-506 (this decision).
- Issues #65 (adapter rules), #70 (D5-11), #130 (DEV-1 services).
