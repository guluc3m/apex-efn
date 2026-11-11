# ADR-306: Treasury projection and offline trust calibration

Status: **Accepted** (TL decision, 2026-11-11, chat). Lane DEV-3, task D3-10.

## Treasury projection (`apex.domain.finance.projection.project_treasury`)
1. Pure, integer minor units. Needs `window` (last N periods with `cash_balance`) and `min_periods` from config; no default in code.
   Fewer periods than `min_periods` raises `ProjectionError` (the spec's 3-period rule: `projection_enabled=false`).
2. Monthly net = `revenue` − (`cogs` + `fixed_costs` + `payroll` + `debt_service` + `capex`). `tax_reserve` is a stock
   (ADR-305 already subtracts it from the capacity) and `accounts_*` are ignored.
3. `months` = whole calendar months from the latest period to the payment date, never negative.
4. `expected = cash + floor(mean(net)) * months`; `pessimistic = cash + min(net) * months`. Floor on the signed mean
   is the conservative side. Wiring the result into `FinancialSnapshot.treasury_minor` (which band to use) is DEV-4's call.

## Trust calibration (`apex.domain.trust.calibration`)
1. Offline and pure. Input: labelled sellers (snapshot, optional reviews, `bad` outcome) of one category.
   `evaluate` returns AUC (ties 1/2) and bad rate per band.
2. `propose_weights` grid-searches the group weights (`step_pct` multiples, sum 100%, `institutional` the heaviest per ADR-304)
   maximising AUC; first candidate wins ties. `insufficient_labels` below `min_bad`/`min_good`; `no_improvement` if none beats the current.
3. It only proposes. Bands and thresholds are not tuned. Applying a proposal is a signed config decision creating a new
   `model_version` (spec §3.4.3), never automatic.
