# ADR-503: Browser worker internal API

## Status

Proposed (DEV-5, D5-01). Contract change: DEV-2 approves (AGENTS.md 3.5).

## Context

D5-01 fills in `contracts/internal/browser-worker.openapi.yaml`, which D2-01 left as a skeleton. Two
callers use it:

- **Scraping (DEV-4, D4-09).** `ScrapingService` calls `BrowserWorkerPort.search()` once per plan step.
  Seller signals and product detail are fetched per seller or product afterwards. A search can take
  seconds to minutes and must survive rate limits, CAPTCHAs and retries.
- **Negotiation (DEV-5, D5-07).** The engine's `ChatTransport` (`open`, `send`, `read`) needs the seller's
  reply before it drafts the next message. A human takeover (D5-08) must stop the agent from sending.

ADR-200 makes the OpenAPI files the only source of DTOs. Until now its generator only read the public
contract.

## Decision

1. **Async jobs for scraping, sync calls for chat.** `POST /internal/v1/jobs` enqueues a BullMQ job
   (`search`, `product`, `seller`, `seller_signals`). `GET /internal/v1/jobs/{id}` returns `JobState` with
   a typed `result` or a typed `error`. Chat operations under `/internal/v1/chats` are synchronous: the
   worker still serialises them per account and per domain internally, but the caller gets the result in
   the response.
2. **Discriminated unions on `kind`.** `JobRequest` and `JobResult` are `oneOf` with a `discriminator`.
   Both generators produce real tagged unions: Zod `discriminatedUnion` in TS, and a Pydantic `RootModel`
   with `Field(discriminator="kind")` in Python. Requests are `additionalProperties: false`.
3. **Raw data only.**
   - Offers carry the listed `unit_price`, `list_price` and `price_tiers` as `Money` in the closed
     `EUR | USD | CNY` enum. No EUR conversion, no bands, no scores.
   - A listing in any other currency, or a listing without a parseable price, is not an offer. It is
     returned in `skipped` with a closed `SkipReason`, so the orchestrator can count and report it.
   - Seller signals mirror the public `SellerSignalSnapshot` fields. A signal the platform does not publish
     is `null`, never `0`. `recent_reviews` (at most 500) feeds the structural manipulation checks in
     spec 3.4.2. `data_completeness` is computed by DEV-3, not by the worker.
4. **Idempotency.** Every write takes `Idempotency-Key`. For `sendChatMessage` this is how "sent at most
   once" survives a retry after a timeout. The engine passes a key derived from the negotiation ID and the
   draft ID. A replay with a different body answers `409 idempotency_conflict`.
5. **Takeover lock in the worker.** `PUT /chats/{id}/lock` gives a human a TTL lock, and
   `DELETE /chats/{id}/lock?user_id=` releases it. While the lock is held, every `sender: agent` send
   answers `409 chat_locked`. A `sender: human` send must come from the lock holder (`409 not_lock_holder`).
   The engine already refuses to send while it is in `human_control`, so this is a second, independent
   barrier at the only place that can actually send.
6. **Credentials never cross the API.** Chats are opened with an opaque `account_id`. The worker reads the
   platform session from Vault itself (D1-06 client).
7. **Service authentication.** Every endpoint except `GET /internal/v1/health` requires a bearer service
   token (`BROWSER_WORKER_TOKEN`, from Vault). It is never a user token. The worker listens on port 4010
   and is not published outside the cluster network.
8. **Errors.** Errors are RFC 9457 `WorkerProblem` with a closed `code` (`WorkerErrorCode`) and
   `retryable` / `retry_after_seconds`. Job failures use the same codes in `JobError`. The D5-10 runbooks
   are keyed by these codes: `session_invalid`, `captcha`, `dom_changed`, `rate_limited`.
9. **Code generation.** `contracts/scripts/generate.mjs` now loops over a list of specs:
   - The public contract generates as before.
   - The internal contract generates TS and Zod into `packages/shared-types/src/generated/browser-worker/`,
     exported as `@apex/shared-types/contracts/browser-worker` and `.../browser-worker/zod`.
   - It generates Pydantic into `apps/orchestrator/src/apex/contracts/generated/browser_worker.py`.
   - The drift check now walks subdirectories.
   - Shared shapes (`Money`, `Currency`, `PriceTier`, `ShippingEstimate`, `Incoterm`) are copied into the
     internal spec rather than referenced across files, because neither generator resolves cross-file
     `$ref` cleanly. They must stay identical to the public ones.
   - Nullable properties use inline `anyOf [$ref, null]`, so Python gets `Money | None` instead of a
     wrapper model.

## Consequences

- DEV-4 can replace `UnwiredBrowserWorker` with an HTTP client built on
  `apex.contracts.generated.browser_worker`, and map `RawOffer` onto its internal `RawOffer`. The field
  names match except `platform` vs. `platform_id` and `platform_seller_id` vs. `seller_id`.
  `quantity_available` is nullable in the contract because most platforms do not show stock.
- The browser worker gains an HTTP server (D5-01 implementation PR) next to its BullMQ workers.
- Any change to the copied shared shapes in the public contract must be mirrored here.
- Hand-written job types in `apps/browser-worker/src/jobs/*.ts` and the legacy `RawSellerSignals` import
  are replaced by the generated types in the implementation PR.

## Related

- ADR-200 (contracts and codegen), ADR-500 (browser stack), ADR-501 and ADR-502 (negotiation), ADR-900 (Q10).
- Issues #60 (D5-01), #67 (D5-08), #69 (D5-10).
