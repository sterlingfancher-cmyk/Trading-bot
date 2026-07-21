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

Version:

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

Version:

`missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`

The forced audit confirmed all six symbols exceeded the 8% move threshold. Five were outside the executable universe and unseen: BE, NVTS, NUAI, CRWV, and ONDS. STX was in the executable universe but had no persisted scanner, decision, blocker, or audit observation.

Route:

`/paper/missed-opportunity-post-close-audit-status`

Forced example:

`/paper/missed-opportunity-post-close-audit-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1&threshold=8`

### Milestone 3 — Shadow liquidity, data quality, and observation trace

Version:

`scanner-v2-shadow-quality-trace-2026-07-21-v1`

The forced quality trace established:

- all six names passed the current shadow liquidity floors;
- all six exceeded minimum price, average-volume, and average-dollar-volume requirements;
- five remain `universe_coverage_miss`;
- STX remains `universe_present_but_no_observation`;
- no symbol had persisted scanner, decision, blocker, dynamic-universe, journal, or post-harvest records.

This evidence shows the primary issue is discovery/observation rather than tradability.

Route:

`/paper/scanner-v2-shadow-quality-trace-status`

Forced example:

`/paper/scanner-v2-shadow-quality-trace-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

### Milestone 4 — Advisory composite scoring and theme leadership

Version:

`scanner-v2-shadow-composite-score-2026-07-21-v1`

A new advisory-only module scores selected shadow candidates using explicit, inspectable components:

- one-day momentum;
- five-day trend;
- relative volume;
- liquidity;
- continuation strength;
- extension penalty;
- reversal penalty.

The module also aggregates symbol scores into theme-leadership diagnostics using:

- average member score;
- positive breadth;
- count of strong members;
- top-ranked members by cluster.

The scoring output is observational only. It does not promote symbols, alter `core.UNIVERSE`, patch `scan_signals`, change risk or sizing, lower thresholds, place orders, or grant ML/live authority.

Route:

`/paper/scanner-v2-shadow-composite-score-status`

Forced six-symbol example:

`/paper/scanner-v2-shadow-composite-score-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

Expected output includes:

- `ranked_candidates`;
- per-symbol `components` and `weights`;
- `composite_score`;
- `theme_leadership`;
- all authority mutation flags false.

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
- `scanner_v2_shadow_composite_score.py`
  - `00214d50538fbc065402c02e6c75cc4d7856debd` — add advisory composite scoring and theme leadership.
- `usercustomize.py`
  - `f1e902d8eb25760f5c8a5ca23989950d8ca8c961` — register quality trace.
  - `4bb58524b1a5cff2ef695729c40633edadb82f4e` — register composite scoring route.
- `PROJECT_HANDOFF.md`
  - this commit records the validated quality findings and Milestone 4.

## Scanner v2 Next Steps

Proceed in this order:

1. Validate `/paper/self-check` after Railway redeploys.
2. Validate the new lightweight composite route and confirm version `scanner-v2-shadow-composite-score-2026-07-21-v1`.
3. Run the forced six-symbol composite report and review candidate ranking, component attribution, extension/reversal penalties, and theme-leadership scores.
4. Instrument advisory candidate-lifecycle persistence for STX and other executable-universe names that leave no scanner record. Trace scanner iteration, data retrieval, prefilter exclusion, signal creation, and audit persistence without changing trade authority.
5. Expand the forced composite sample across the full shadow leadership baskets and multiple sessions.
6. Record repeated candidate-to-entry and candidate-to-outcome attribution against the current rule engine.
7. Add regime-aware shadow weighting only after the unweighted baseline is captured.
8. Only after repeated evidence demonstrates improved capture without unacceptable false positives, extension chasing, drawdown, or loss clustering, prepare a separately reviewed paper-only promotion gate.
9. Add BTC, ETH, and SOL later through a separate provider and crypto-specific volatility milestone.

No filter should be relaxed solely because a stock finished strongly.

## Remaining Project Priorities

### Shared cycle identity

Propagate one immutable `cycle_id` through scanner output, decision audit, blocked-entry audit, X-Ray, entries, rotations, and post-harvest after Scanner v2 shadow instrumentation is stable.

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

Then inspect the lightweight route:

`https://trading-bot-clean.up.railway.app/paper/scanner-v2-shadow-composite-score-status`

Expected:

- `status: ok`;
- `overall: pass`;
- `version: scanner-v2-shadow-composite-score-2026-07-21-v1`;
- `mode: advisory_shadow_only`;
- `market_data_requested: false`;
- all authority mutation flags false.

For deliberate post-close analysis, use:

`https://trading-bot-clean.up.railway.app/paper/scanner-v2-shadow-composite-score-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

Review `ranked_candidates`, each row's `components`, `weights`, `composite_score`, and `theme_leadership`.
