# ADR-303: Seller confidence: signal count, data completeness and the manipulation rubric

## Status

Proposed (D3-06). Needs TL approval.

## Context

Spec §3.4.2 says `data_completeness < seller.min_signals` gives `insufficient_data`, but `min_signals` defaults to
`3` while `data_completeness` is a ratio. ADR-900 Q3 settled it: `min_signals` counts present raw signals. The
spec also lists five structural manipulation checks without defining them, and the snapshot in the contract
carries no review time series.

## Decision

1. **Signal count.** A raw signal is one of the 21 fields of spec §3.4.1 (`account_age_days` … `refund_rate`).
   It is present when it is not null (`gmv_12m`: when the money value is not null). `seller.min_signals` is
   compared with that count. Below it the engine returns `insufficient_data`, `score: null`, no normalised
   signals and no flags. `data_completeness` stays a reported ratio (present / 21), computed by the caller and
   never used to decide.
2. **Inputs.** `compute(snapshot, cfg, *, now, reviews=None)`. `now` only stamps `computed_at` and
   `detected_at`; every date computation uses `snapshot.captured_at`, so the result depends on the snapshot
   alone. `reviews` is the list of reviews the adapter saw (`rating`, `date`, `verified`, `text`). Without it
   only the `low_verified_share` check runs and the output carries the penalty `reviews_unavailable`, so
   nobody mistakes "not checked" for "clean". `gmv_12m` must already be in EUR (`gmv_not_eur` otherwise): the
   TrustAgent converts it with `apex.domain.fx` at ingestion.
3. **Manipulation rubric.** Structure only, never the meaning of the text. Every flag is `critical` and caps the
   band at `low` (`untrusted` stays `untrusted`). All z-tests use `seller.review_burst_z`.
   - `burst_velocity`: reviews of the last 360 days in twelve 30-day buckets back from `captured_at`. z of the
     busiest bucket against the mean and population sd of the other eleven.
   - `creation_correlation`: reviews in 30-day buckets forward from the account creation date
     (`captured_at − account_age_days`), full buckets only, at least three. z of the first bucket against the
     rest.
   - `five_star_anomaly`: one-sided binomial z of the 5-star share against
     `seller.category_five_star_share`.
   - `low_verified_share`: `verified_review_share < seller.min_verified_share`.
   - `duplicate_text`: texts lower-cased with whitespace collapsed, empty ones ignored. The share of texts
     that occur more than once is above `seller.max_duplicate_text_share`. "Generic" text detection needs a
     word list or a model, so it is left out.
   - The sd in the velocity tests is floored at 1 review, so a seller going from 0 to 1 review a month is not
     a burst. The 30-day bucket is part of the algorithm, not a tenant threshold.
4. **Version.** `model_version = "seller-confidence@1/<config_version>"`. The engine part changes when the
   algorithm changes, the config part when weights or thresholds change, so every evaluation names both.

## Consequences

- The manipulation checks only work once adapters pass reviews. The mock marketplace already has them
  (`ReviewSchema`); DEV-4 passes them from the TrustAgent (issue linked in the D3-06 PR).
- New config keys are needed (`category_five_star_share`, `min_verified_share`, `max_duplicate_text_share`),
  proposed in ADR-304.

## Related

- Spec §3.4.1–3.4.3, §9 criteria 6–9; ADR-900 Q3, Q13; ADR-300; ADR-304
