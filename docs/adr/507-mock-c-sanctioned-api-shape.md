# ADR-507: `mock-c`, the sanctioned-API shape

## Status

Accepted (DEV-5, D5-11). Revisit when a real platform grants API access.

## Context

D5-11 asks for autonomous sending "on one real platform". Every platform we checked forbids automating the web
front end (see `docs/compliance/wallapop.md`, ADR-506, and the eBay/Vinted/Alibaba findings): the prohibition is
on the activity, and a proxy or a browser session does not change it. The one sanctioned negotiation channel we
found is an **official API with a buyer→seller messaging resource** — Mercado Libre's `/questions`, and the
partner/Open-Platform APIs of the B2B platforms.

The product needs a platform it can demo and test against *now*: something with volume pricing, seller signals and
a real conversation, without pretending a real marketplace said yes.

## Decision

Add a third platform to the mock marketplace: **`mock-c`**, an API-first B2B marketplace.

- **Wire shape:** the shape we would consume from a sanctioned API — search, item, supplier and supplier-metrics
  endpoints, plus `threads` / `threads/{id}/messages` for the negotiation. Integer cents, basis points, ISO dates,
  a closed `{ error: { code } }` envelope. Deliberately *not* mock-a's decimal strings or mock-b's HTML.
- **Negotiation is an API call**, not a browser: `POST /threads`, `POST /threads/{id}/messages`,
  `GET /threads/{id}/messages?after_seq=`. The buyer asks, the supplier answers, no login and no DOM.
- **The same persona engine** answers as the seller, so the negotiation, adversarial and semi-automatic suites run
  against it unchanged, and `negotiation.autonomous_send` finally has a platform to send on.
- **Synthetic data only** (`fixtures/sellers.json`, `fixtures/products.json`), covered by
  `docs/compliance/mock-marketplace.md`.
- **The adapter passes the shared `PlatformAdapter` contract suite**, so switching to a real API is a mapping
  change, not a redesign.

## Consequences

- We can prove the end-to-end loop — discovery, seller confidence, negotiation, approval/autonomous mode, gate —
  without violating anyone's terms and without a partner agreement.
- The mock is **not** evidence that a real platform permits this. Nothing here weakens ADR-506: a Wallapop or
  Vinted mission still fails closed.
- `mock-c` costs one platform implementation and one adapter, both of which are the code we keep when a partner
  API appears: the transport changes, the mapping and the contract suite stay.
- The `platform.mock-c.enabled` flag and the `MOCK_C_BASE_URL` env var gate it exactly like the other mocks.

## Related

- ADR-500 (browser stack), ADR-505 (`mock-b` over HTTP), ADR-506 (Wallapop is not automated), ADR-900 (Q10).
- `docs/compliance/mock-marketplace.md`, issue #70, DEV-6's end-to-end suite (D6-08).
