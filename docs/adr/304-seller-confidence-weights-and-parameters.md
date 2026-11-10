# ADR-304: Seller confidence: default weights, saturation points and parameters

## Status

Proposed (D3-06). Needs TL approval. Until it is approved, `seller.weights` stays unset and the trust engine
refuses to run (`config_unset`), as ADR-900 Q3 intends.

## Context

Spec §3.4.2 makes the score `round(100 · Σ w_i · f_i)` over five signal groups, with institutional guarantees
weighing more than volume (ADR-900 Q3). It leaves the weights, the saturation point `x_sat` of each count and
several thresholds to an ADR. Every value below is a **proposal** for the TL; the code has no defaults.

## Decision

1. **Group score.** Each group is the mean of its scored signals. An absent signal scores 0, so missing data
   never raises a score. The weights must add up to exactly 1 (checked in decimal).

   | Group (`seller.weights.*`) | Proposed weight | Scored signals and normalisation                                                                                                                                                                                |
   | -------------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | `institutional`            | **0.30**        | `identity_verified`, `trade_assurance`, `escrow_available`: 1 or 0                                                                                                                                              |
   | `reviews`                  | **0.25**        | `rating_adjusted` = (Bayesian rating − 1) / 4; `positive_share_wilson` (4–5★, Wilson lower bound at `seller.wilson_confidence`); `reviews_total`, `reviews_12m` (log); `verified_review_share`, `response_rate` |
   | `sales`                    | **0.20**        | `lifetime_transactions`, `transactions_12m`, `gmv_12m` (log); `repeat_buyer_share`                                                                                                                              |
   | `age`                      | **0.15**        | `account_age_days`, days since `first_sale_date` (linear up to `seller.age_saturation_days`); `months_active_last_12` / 12                                                                                      |
   | `catalog`                  | **0.10**        | `published_products_count` (log); 1 − `catalog_churn_30d`; `spec_completeness_avg`                                                                                                                              |

   `rating_count` feeds the shrinkage. `dispute_rate` and `refund_rate` are not scored: above
   `seller.max_dispute_rate` the weighted sum is multiplied by `max_dispute_rate / worst_rate` (a rate twice
   the maximum halves the score) and the penalty is listed.

2. **Saturation points** (`seller.x_sat.*`, log scale `log10(1 + x) / log10(1 + x_sat)`, capped at 1):
   `lifetime_transactions` 10 000, `transactions_12m` 2 000, `gmv_12m` EUR 1 000 000, `published_products_count`
   500, `reviews_total` 1 000, `reviews_12m` 250.
3. **Other new keys** (scope tenant unless noted):
   - `seller.category_rating_mean` (tenant/category) **4.5**: the prior `m` of the shrinkage. It moves to the
     D2-13 analytics store when category statistics exist.
   - `seller.category_five_star_share` (tenant/category) **0.6**.
   - `seller.wilson_confidence` **0.95** (spec §3.4.2 says 95%). z comes from the inverse normal CDF.
   - `seller.min_verified_share` **0.3**, `seller.max_duplicate_text_share` **0.2**.
   - Existing keys keep the spec §7 defaults: `rating_prior_weight` 25, `age_saturation_days` 730,
     `min_signals` 3, bands 75/50/25, `hard_block_below` 20, `review_burst_z` 3.0, `max_dispute_rate` 0.05.
4. **Bands.** `untrusted` when score < `band_low` **or** < `hard_block_below`, then `high` ≥ `band_high`,
   `medium` ≥ `band_medium`, else `low`. Any manipulation flag caps the result at `low` (ADR-303).

## Consequences

- With these values, a seller with KYC, trade assurance and escrow and nothing else scores 35 (`low`): the
  guarantees count, but they cannot buy a pass without track record. One 5.0 review scores below 500 reviews
  at 4.8 (criterion 7), shown in `packages/test-vectors/trust/compute.json`.
- DEV-4 adds the keys to `/config/defaults/tenant-config.v1.json` and the contract `SellerConfig` once the TL
  approves (issue linked in the D3-06 PR). Changing any of them is a signed config decision with a new
  `config_version`, so `model_version` changes too.

## Related

- Spec §3.4.2, §7; ADR-900 Q3; ADR-303; TL notes §7
