# Automated Trading Project Handoff — Updated July 21, 2026

## Standing Rule

Every code/configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Full diagnostics: `https://trading-bot-clean.up.railway.app/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## Latest Validated Runtime Baseline

The compact self-check previously passed with `overall: pass`, `status: ok`, no warnings, a stable recursion-safe direct-core entry pipeline, no newly timestamped duplicate-reason or recursion error, paper equity of 10864.08, and 83 execution rows.

Routine validation remains `/paper/self-check`; use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error.

## Active Workstream — Scanner v2

### Milestone 1 — Expanded shadow universe

Current version:

`scanner-v2-shadow-universe-2026-07-21-v2-leadership-clusters`

The advisory taxonomy includes AI/data-center infrastructure, power/electrification, semiconductor power/components, autonomy/drones/sensing, robotics, defense, energy, metals, healthcare, quantum, and broad liquid indexes.

Confirmed missed movers represented in the shadow taxonomy:

- BE — power/electrification
- NVTS — semiconductor power/components
- STX — AI/data-center infrastructure
- NUAI — power/electrification
- CRWV — AI/data-center infrastructure
- ONDS — autonomy/drones/sensing

Route:

`/paper/scanner-v2-shadow-universe-status`

### Milestone 2 — Missed-opportunity post-close audit

Current version:

`missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`

The first forced post-close audit confirmed all six symbols exceeded the 8% move threshold. Five were outside the executable universe and unseen: BE, NVTS, NUAI, CRWV, and ONDS. STX was in the executable universe but had no persisted scanner, decision, blocker, or audit observation.

The audit distinguishes:

- `universe_coverage_miss`
- `universe_present_but_no_observation`
- `seen_but_not_entered`
- `captured_position`
- `outside_observed_pipeline`

Route:

`/paper/missed-opportunity-post-close-audit-status`

Forced example:

`/paper/missed-opportunity-post-close-audit-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1&threshold=8`

### Milestone 3 — Shadow liquidity, data quality, and observation trace

Current version:

`scanner-v2-shadow-quality-trace-2026-07-21-v1`

A new advisory-only trace evaluates selected symbols against the current shadow quality floors:

- minimum price: 3.00
- minimum average daily volume: 350,000
- minimum average dollar volume: 5,000,000

When deliberately called with `force=1`, it reports:

- current price;
- one-day and five-day change;
- current volume;
- 20-day average volume;
- relative volume;
- average dollar volume;
- whether the symbol passes the shadow liquidity floor.

It also traces persisted scanner, decision, blocker, dynamic-universe, journal, and post-harvest sections and classifies each symbol as:

- `universe_coverage_miss`;
- `universe_present_but_no_observation`;
- `observed_without_records`;
- `observed_with_records`.

This directly addresses the STX failure mode without altering scanner execution. For a universe-present symbol with no observation, the recommended next trace is candidate-lifecycle persistence inside `scan_signals`.

Route:

`/paper/scanner-v2-shadow-quality-trace-status`

Forced six-symbol example:

`/paper/scanner-v2-shadow-quality-trace-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

## Safety Boundary

All Scanner v2 modules remain observational:

- `core.UNIVERSE` is not mutated;
- `scan_signals` is not patched;
- no orders are placed;
- no thresholds are changed;
- no sizing or risk controls are changed;
- no ML authority is changed;
- no live authority is granted;
- heavy external market-data work occurs only when a route is explicitly called with `force=1`.

Executable-universe expansion remains deferred until repeated evidence supports a separately reviewed paper-only promotion gate.

## Files Changed and Commits

- `scanner_v2_shadow_universe.py`
  - `227ac0d4d559e0aff1140456b48bbc54ad6fd36b` — initial advisory shadow universe.
  - `50d84797c093aa6aeb90c1b0fd9b5da5027eb7aa` — confirmed leadership clusters and missed movers.
- `missed_opportunity_post_close_audit.py`
  - `fbdfab96d46a834efa0844da8a428032640a283d` — initial post-close audit.
  - `e8295b01a1e21b7e20850196a812c4925488ab1f` — separate universe and observation failure modes.
- `scanner_v2_shadow_quality_trace.py`
  - `c4321dba229a0b3d12020e4464597f810014ae5a` — add shadow liquidity/data-quality and observation trace.
- `usercustomize.py`
  - `f1e902d8eb25760f5c8a5ca23989950d8ca8c961` — register the new optional route and module.
- `PROJECT_HANDOFF.md`
  - this commit records Milestone 3, validation links, and the revised next sequence.

## Scanner v2 Next Steps

Proceed in this order:

1. Validate `/paper/self-check` after Railway redeploys.
2. Validate all three Scanner v2 advisory routes and confirm current versions.
3. Run the forced shadow-quality trace for BE, NVTS, STX, NUAI, CRWV, and ONDS.
4. Confirm which universe misses pass the existing liquidity/data-quality floors.
5. Confirm whether STX remains `universe_present_but_no_observation` after redeployment and a subsequent scanner cycle.
6. If STX remains unobserved, add advisory candidate-lifecycle persistence around scanner iteration, data retrieval, prefilter exclusion, signal creation, and audit write stages.
7. Add composite opportunity-score attribution in shadow mode: trend, relative strength, volume, momentum, market alignment, extension risk, liquidity, and quality.
8. Add theme-leadership scoring so multiple strong members can elevate a cluster without automatically making any symbol executable.
9. Accumulate repeated post-close samples across multiple sessions and regimes.
10. Add candidate-to-entry and candidate-to-outcome attribution against the current rule engine.
11. Only after repeated evidence supports improvement, prepare a separately reviewed paper-only promotion gate for selected shadow candidates.
12. Add BTC, ETH, and SOL later through a separate provider and crypto-specific volatility milestone.

No filter should be relaxed solely because a stock finished strongly. Changes must show improved opportunity capture without unacceptable extension chasing, false positives, drawdown, or loss clustering.

## Remaining Project Priorities

### Shared cycle identity

Propagate one immutable `cycle_id` through scanner output, decision audit, blocked-entry audit, X-Ray, entries, rotations, and post-harvest after the Scanner v2 shadow instrumentation is stable.

### Phase 3A ML advisory evaluation

Continue ML in advisory-only paper mode. Rule thresholds and hard risk controls remain authoritative. Log ML-versus-rules disagreement and outcomes; do not increase authority before the evidence benchmark and repeatable improvement are demonstrated.

## Validation Procedure

After Railway redeploys, run:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- `overall: pass`;
- `status: ok`;
- `health.warnings: []`;
- stable entry-pipeline fields remain true;
- no newly timestamped runtime error.

Then inspect:

`https://trading-bot-clean.up.railway.app/paper/scanner-v2-shadow-universe-status`

Expected version:

`scanner-v2-shadow-universe-2026-07-21-v2-leadership-clusters`

Inspect:

`https://trading-bot-clean.up.railway.app/paper/missed-opportunity-post-close-audit-status`

Expected version:

`missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`

Inspect the lightweight new route:

`https://trading-bot-clean.up.railway.app/paper/scanner-v2-shadow-quality-trace-status`

Expected:

- `status: ok`;
- `overall: pass`;
- `version: scanner-v2-shadow-quality-trace-2026-07-21-v1`;
- `mode: advisory_shadow_only`;
- all authority mutation flags false.

For deliberate post-close analysis, use:

`https://trading-bot-clean.up.railway.app/paper/scanner-v2-shadow-quality-trace-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

Review each row's `observation_classification`, `section_hits`, `records`, `market_snapshot`, `shadow_liquidity_pass`, and `recommended_next_trace`.
