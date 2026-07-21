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

The compact self-check previously passed with:

- `overall: pass`
- `status: ok`
- `health.warnings: []`
- stable, recursion-safe, direct-core entry pipeline
- no newly timestamped duplicate-reason or recursion error
- paper account equity 10864.08 with 83 execution rows

Routine validation remains `/paper/self-check`; use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error.

## Active Workstream — Scanner v2

### Milestone 1 — Expanded shadow universe

Current version:

`scanner-v2-shadow-universe-2026-07-21-v2-leadership-clusters`

The advisory-only shadow taxonomy now includes:

- AI and data-center infrastructure;
- power and electrification;
- semiconductor power and components;
- autonomy, drones, and sensing;
- robotics and automation;
- defense and aerospace;
- energy leaders;
- precious metals;
- healthcare leaders;
- quantum computing;
- broad liquid indexes and sector ETFs.

The six confirmed missed movers are explicitly represented:

- BE — power/electrification;
- NVTS — semiconductor power/components;
- STX — AI/data-center infrastructure;
- NUAI — power/electrification;
- CRWV — AI/data-center infrastructure;
- ONDS — autonomy/drones/sensing.

Route:

`/paper/scanner-v2-shadow-universe-status`

The route reports current-universe overlap, new shadow candidates, basket membership, and the confirmed missed movers that remain outside the executable universe.

### Milestone 2 — Missed-opportunity post-close audit

Current version:

`missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`

The first forced post-close audit confirmed all six symbols exceeded the 8% move threshold:

- BE +14.82%;
- NVTS +11.14%;
- STX +11.14%;
- NUAI +14.76%;
- CRWV +8.92%;
- ONDS +11.50%.

Observed failure modes:

- Five symbols were outside the executable universe and had no scanner/audit observation: BE, NVTS, NUAI, CRWV, ONDS.
- STX was already in the executable universe but had no persisted scanner, decision, blocker, or audit observation.
- No symbol became an open position.

The audit now separates these cases explicitly:

- `universe_coverage_miss` — outside executable universe and unseen;
- `universe_present_but_no_observation` — in executable universe but no persisted scanner/decision evidence;
- `seen_but_not_entered` — observed but not converted;
- `captured_position` — present in open positions;
- `outside_observed_pipeline` — residual fallback classification.

Each row also reports a theme cluster and a diagnostic next step.

Route:

`/paper/missed-opportunity-post-close-audit-status`

Forced example:

`/paper/missed-opportunity-post-close-audit-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1&threshold=8`

## Safety Boundary

Both Scanner v2 modules remain strictly observational:

- `core.UNIVERSE` is not mutated;
- `scan_signals` is not patched;
- no orders are placed;
- no thresholds are changed;
- no sizing or risk controls are changed;
- no ML authority is changed;
- no live authority is granted.

The direct executable-universe expansion remains deferred until repeated evidence supports a separately reviewed paper-only promotion gate.

## Files Changed and Commits

- `scanner_v2_shadow_universe.py`
  - `227ac0d4d559e0aff1140456b48bbc54ad6fd36b` — initial advisory shadow universe.
  - `50d84797c093aa6aeb90c1b0fd9b5da5027eb7aa` — add confirmed leadership clusters and missed movers.
- `missed_opportunity_post_close_audit.py`
  - `fbdfab96d46a834efa0844da8a428032640a283d` — initial post-close audit.
  - `e8295b01a1e21b7e20850196a812c4925488ab1f` — separate universe-coverage and observation failure modes.
- `usercustomize.py`
  - `465e70b4953b2129761582d89a57717e4714ba16` — register audit route and optional self-check endpoint.
- `PROJECT_HANDOFF.md`
  - this commit records the validated audit findings and revised Scanner v2 sequence.

## Scanner v2 Next Steps

Proceed in this order:

1. Validate `/paper/self-check` after Railway redeploys.
2. Validate both Scanner v2 routes and confirm the new versions.
3. Re-run the forced six-symbol audit and confirm five `universe_coverage_miss` rows and one `universe_present_but_no_observation` row for STX, unless new runtime telemetry changes the evidence.
4. Add shadow data-quality and liquidity evaluation across the expanded leadership clusters.
5. Add composite opportunity-score attribution in shadow mode: trend, relative strength, volume, momentum, market alignment, extension risk, liquidity, and quality.
6. Add theme-leadership scoring so multiple strong members can elevate a cluster without automatically making any symbol executable.
7. Investigate the STX observation gap by tracing scanner iteration, data availability, and persistence paths.
8. Accumulate repeated post-close samples across multiple sessions and regimes.
9. Add candidate-to-entry and candidate-to-outcome attribution against the current rule engine.
10. Only after repeated evidence supports improvement, prepare a separately reviewed paper-only promotion gate for selected shadow candidates.
11. Add BTC, ETH, and SOL later as a separate provider and volatility-handling milestone rather than forcing them through equity-only assumptions.

No filter should be relaxed solely because a stock finished strongly. Changes must show improved opportunity capture without unacceptable extension chasing, false positives, drawdown, or loss clustering.

## Remaining Project Priorities

### Shared cycle identity

Propagate one immutable `cycle_id` through scanner output, decision audit, blocked-entry audit, X-Ray, entries, rotations, and post-harvest after the initial Scanner v2 shadow instrumentation is stable.

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

Then inspect:

`https://trading-bot-clean.up.railway.app/paper/missed-opportunity-post-close-audit-status`

Expected version:

`missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`

For deliberate post-close investigation, use the forced audit route and review `diagnostic_classification`, `theme_cluster`, `section_hits`, `observed_reasons`, `market_snapshot`, and `recommended_diagnostic_next_step`.