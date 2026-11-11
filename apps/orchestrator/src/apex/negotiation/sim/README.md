# Simulation: a fake marketplace with AI on both sides

Demo harness (D5-11). No real marketplace, no real LLM vendor, no database, no Docker: a fast fake
marketplace, an LLM stub that repeats the prices the code decides, three AI buyers negotiating through the
real engine, and a page to watch it.

## Run it

```bash
./apps/orchestrator/src/apex/negotiation/sim/demo.sh
# open http://127.0.0.1:8003
```

Or start the pieces yourself:

| Piece | Command | Port |
|---|---|---|
| LLM stub | `cd apps/llm-stub && uv run python -m llm_stub` | 8001 |
| Fake marketplace | `cd apps/mock-marketplace && pnpm dev` | 8002 |
| Simulation UI | `cd apps/orchestrator && uv run python -m apex.negotiation.sim.server` | 8003 |
| CLI instead of the page | `cd apps/orchestrator && uv run python -m apex.negotiation.sim run --json report.json` | — |

## What happens in a run

Each AI buyer has a budget profile (quantity, target and maximum discount). The pipeline:

1. searches the fake marketplace (`mock-c` API) and picks a supplier: cheapest offer in the buyer's currency,
   tie-broken by the supplier's rating;
2. opens a negotiation thread and drives the real `NegotiationEngine` in autonomous mode — the playbook picks
   every price, the LLM stub only writes the words;
3. ends with `agreed`, `escalated` (the seller held above the target but below the list price, so the human gate
   gets it), or `no agreement`;
4. records every step and the whole conversation in a `ScenarioReport`, which is what the page renders.

The seller side is the marketplace's persona engine. Its numbers are deterministic; when `SIM_LLM_URL` is set
the wording is rephrased by the stub, and a rephrasing that changes the price is rejected and replaced by the
scripted text.

## What this is not

It is not a permission to automate a real platform. Wallapop and Vinted forbid it (ADR-506 and
`docs/compliance/`); Alibaba and eBay forbid scraping and are partner-gated. This harness exists so the loop can
be demonstrated and regression-tested without pretending otherwise.
