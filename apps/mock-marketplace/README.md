# @apex/mock-marketplace

Synthetic marketplace for tests, E2E and demos (task D5-04). Two fake platforms, synthetic seller and
product fixtures, and scripted chat personas. **Never deploy it and never point it at real data.**

```bash
pnpm --filter @apex/mock-marketplace dev     # http://localhost:8002
pnpm --filter @apex/mock-marketplace test
```

Environment: `PORT` (default `8002`), `HOST` (default `0.0.0.0`), `MOCK_MARKETPLACE_SEED` (default `0`),
`SIM_LLM_URL` (optional).

## Optional LLM rephrasing (`SIM_LLM_URL`)

When `SIM_LLM_URL` points at an OpenAI-compatible stub (for example `http://localhost:8003`, D4-02), each
scripted seller reply is rephrased into one short message in the seller's language before it is stored:

- Only the **wording** comes from the model. Personas still decide the round, the concession and the price,
  and the quote state is untouched.
- The rephrased text is accepted only if it states the same price (currency + amount, formatted as
  `EUR 4.32`, `€4.32` or `4,32 EUR`) and adds no other price. Otherwise, on error, or after 600 ms, the
  scripted text is used.
- Unset or blank means exactly the old deterministic behaviour: scripted text, no HTTP call.

Never point it at a real model endpoint, and keep it out of production: this app is a test double.

## Platforms

Both platforms render the same fixtures in different wire formats, so adapters do real mapping work.

### `mock-a`: JSON API (`transport: http`)

Its own snake_case vocabulary. Money is a decimal string plus a currency, dates are epoch seconds, and the
rating is on a 0-100 scale.

| Method | Path                                            | Notes                                     |
| ------ | ----------------------------------------------- | ----------------------------------------- |
| GET    | `/mock-a/api/search?q=&page=`                   | 20 per page                               |
| GET    | `/mock-a/api/products/:id`                      | bulk pricing, delivery, trade term        |
| GET    | `/mock-a/api/sellers/:id`                       | profile                                   |
| GET    | `/mock-a/api/sellers/:id/metrics`               | raw seller signals, `null` when not shown |
| GET    | `/mock-a/api/sellers/:id/reviews`               | individual reviews                        |
| POST   | `/mock-a/api/conversations`                     | `{vendor_id, listing_id}` → 201           |
| POST   | `/mock-a/api/conversations/:id/messages`        | `{body}` → 201                            |
| GET    | `/mock-a/api/conversations/:id/messages?after=` | messages after a sequence number          |

### `mock-b`: server-rendered HTML (`transport: browser` for chat)

No client JavaScript. A plain HTTP crawler can read every page. The chat uses ordinary HTML forms (post,
then 303 redirect), so Playwright drives it with `fill` + `click`. Stable hooks are `data-testid` and `data-*`
attributes. Dates are shown as `DD/MM/YYYY`, and prices with a symbol.

`/mock-b/`, `/mock-b/search?q=`, `/mock-b/item/:id`, `/mock-b/shop/:id`, `POST /mock-b/chat`,
`/mock-b/chat/:id`, `POST /mock-b/chat/:id/send`.

## Fixtures (`fixtures/*.json`, validated with zod at startup)

- Sellers covering every profile: `solid_veteran` (500 reviews at 4.8), `single_perfect_review` (1 review at 5.0),
  `manipulated_reviews` (burst right after account creation, duplicate texts, few verified),
  `insufficient_data`, `high_disputes`, and `standard`.
- Products for `nitrile-gloves-m-box100` on both platforms (at least 3 each, criterion 3), including a −90%
  outlier, a +200% outlier, and an offer in GBP (unsupported currency). Also `kraft-box-30x20x15`.

## Chat personas

Each seller has a default persona. Personas are deterministic: the same seed and the same buyer messages
always give the same transcript.

| Persona                | Behaviour                                                                     |
| ---------------------- | ----------------------------------------------------------------------------- |
| `cooperative`          | volume tiers, decreasing counter-offers down to a floor, written confirmation |
| `aggressive`           | small concessions, "close TODAY" pressure from round 2                        |
| `evasive`              | never states a price                                                          |
| `off_platform`         | asks to move to WhatsApp or a direct bank transfer                            |
| `sensitive_data`       | asks for tax ID, bank details, passport                                       |
| `lowball`              | quotes an anomalously low price                                               |
| `chinese`              | replies in Chinese                                                            |
| `truncated`            | cuts replies mid-sentence                                                     |
| `unsupported_currency` | quotes in GBP until asked for EUR/USD/CNY                                     |

## Test control surface (`/__control/*`, disallowed in robots.txt)

Only tests and the adversarial suite (D5-09) may use it. Adapters must never use it.

- `POST /__control/reset` `{seed?}`: clears every chat and optionally changes the seed.
- `PUT /__control/sellers/:sellerId/persona` `{persona}`: the persona for chats opened afterwards.
- `PUT /__control/chats/:chatId/persona` `{persona}`: switches an open chat.
- `GET /__control/chats`, `GET /__control/chats/:chatId`: transcript plus the seller's ground truth
  (`lastQuote`, `agreed`, `floor`, `flags`). Use it to assert what was really offered.

See `docs/compliance/mock-marketplace.md` and `docs/adr/500-browser-stack-crawler-and-camoufox.md`.
