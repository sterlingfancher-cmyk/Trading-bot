# Automated Trading Project Handoff — Updated July 21, 2026

## Standing Rule

Every code/configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `/paper/self-check`
- Full diagnostics: `/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## Latest Runtime Baseline

The compact self-check previously passed with `overall: pass`, `status: ok`, no warnings, a stable recursion-safe direct-core entry pipeline, no newly timestamped duplicate-reason or recursion error, paper equity of 10864.08, and 83 execution rows.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error.

## Scanner v2 Evidence

The July 21 missed-opportunity sample included BE, NVTS, STX, NUAI, CRWV, and ONDS.

Validated findings:

- all six exceeded the 8% daily-move threshold;
- all six passed minimum price, average-volume, and average-dollar-volume floors;
- BE, NVTS, NUAI, CRWV, and ONDS were executable-universe coverage misses;
- STX was in the executable universe but had no persisted scanner, decision, blocker, or audit observation;
- no symbol became an open position.

The issue is therefore discovery and observation, not basic tradability.

## Current Scanner v2 Modules

### 1. Expanded shadow universe

Version:

`scanner-v2-shadow-universe-2026-07-21-v2-leadership-clusters`

Route:

`/paper/scanner-v2-shadow-universe-status`

Covers AI/data-center infrastructure, power/electrification, semiconductor power/components, autonomy/drones/sensing, robotics, defense, energy, metals, healthcare, quantum, and broad liquid indexes.

### 2. Missed-opportunity post-close audit

Version:

`missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`

Route:

`/paper/missed-opportunity-post-close-audit-status`

Forced sample:

`/paper/missed-opportunity-post-close-audit-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1&threshold=8`

### 3. Shadow liquidity and observation trace

Version:

`scanner-v2-shadow-quality-trace-2026-07-21-v1`

Route:

`/paper/scanner-v2-shadow-quality-trace-status`

Forced sample:

`/paper/scanner-v2-shadow-quality-trace-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

### 4. Advisory composite scoring

Version:

`scanner-v2-shadow-composite-score-2026-07-21-v1`

Route:

`/paper/scanner-v2-shadow-composite-score-status`

Forced sample:

`/paper/scanner-v2-shadow-composite-score-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

Observed ranking:

1. NUAI — 0.923183
2. ONDS — 0.782914
3. STX — 0.634695
4. NVTS — 0.539707
5. BE — 0.530195
6. CRWV — 0.516349

The initial theme aggregation exposed a sample-size problem: one-symbol themes could appear stronger than broader themes because breadth confidence was not represented.

### 5. Confidence-adjusted theme leadership

Version:

`scanner-v2-theme-confidence-overlay-2026-07-21-v1`

Route:

`/paper/scanner-v2-theme-confidence-status`

Forced sample:

`/paper/scanner-v2-theme-confidence-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`

This overlay adds:

- sample-size confidence;
- confidence-adjusted leadership score;
- positive-breadth ratio;
- strong-member ratio;
- `single_member_signal`, `partial_confirmation`, or `broad_confirmed` classification;
- minimum two scored members before a theme is considered confirmed.

Single-member themes remain observations and cannot be treated as confirmed leadership.

### 6. Candidate lifecycle trace

Version:

`scanner-v2-candidate-lifecycle-trace-2026-07-21-v1`

Route:

`/paper/scanner-v2-candidate-lifecycle-trace-status`

This is pass-through diagnostic instrumentation around `scan_signals`. It records:

- whether each tracked symbol was present in `core.UNIVERSE` when a scan began;
- whether the completed scan returned it as a long or short signal;
- whether the scan completed without a signal;
- scanner exceptions, while re-raising them unchanged.

It does not alter scanner arguments or results. Its immediate purpose is to determine whether STX reaches scanner invocation and exits with no signal, or disappears earlier because the active universe differs from the post-close inspection.

## Safety / Authority Boundary

Current Scanner v2 work preserves:

- no live authority;
- no ML execution authority;
- no order placement;
- no threshold changes;
- no sizing or risk-control changes;
- no executable-universe mutation by Scanner v2 modules;
- no signal-result modification;
- existing cooldown, self-defense, drawdown, regime, trend, volume, relative-edge, extension, quality, and futures-bias controls.

The lifecycle module wraps `scan_signals` only for pass-through diagnostics. `alters_scan_result` must remain false.

Executable-universe expansion remains deferred until repeated evidence supports a separately reviewed paper-only promotion gate.

## Files and Commits

- `scanner_v2_shadow_universe.py`
  - `227ac0d4d559e0aff1140456b48bbc54ad6fd36b`
  - `50d84797c093aa6aeb90c1b0fd9b5da5027eb7aa`
- `missed_opportunity_post_close_audit.py`
  - `fbdfab96d46a834efa0844da8a428032640a283d`
  - `e8295b01a1e21b7e20850196a812c4925488ab1f`
- `scanner_v2_shadow_quality_trace.py`
  - `c4321dba229a0b3d12020e4464597f810014ae5a`
- `scanner_v2_shadow_composite_score.py`
  - `00214d50538fbc065402c02e6c75cc4d7856debd`
- `scanner_v2_candidate_lifecycle_trace.py`
  - `fd2a2df4d0a11e6dd48332b5ff7038c3f309bb13`
- `scanner_v2_theme_confidence_overlay.py`
  - `31b96cf50e0876bc97ce002610a795c1eb2a2f59`
- `usercustomize.py`
  - `147101f2c34a3be6b33611549271fc8d5d730757`
- `PROJECT_HANDOFF.md`
  - this commit records the confidence and lifecycle milestone.

## Next Steps

Proceed in this order:

1. Run `/paper/self-check` after Railway redeploys and confirm the existing pass/ok baseline.
2. Validate `/paper/scanner-v2-theme-confidence-status` with and without `force=1`.
3. Allow at least one normal scanner cycle to complete.
4. Inspect `/paper/scanner-v2-candidate-lifecycle-trace-status` and verify STX reports `in_universe_at_scan_start` plus either `returned_long_signal`, `returned_short_signal`, or `scan_completed_no_signal`.
5. Expand forced composite scoring to full theme baskets so leadership confidence is based on multiple members rather than the six-symbol sample.
6. Add repeated candidate-to-entry and candidate-to-outcome attribution.
7. Add regime-aware shadow weighting only after the unweighted baseline is accumulated.
8. Prepare a separately reviewed paper-only promotion gate only after repeated evidence demonstrates better capture without unacceptable false positives, extension chasing, drawdown, or loss clustering.
9. Add BTC, ETH, and SOL later through a separate provider and crypto-specific volatility milestone.

No filter should be relaxed solely because a stock finished strongly.

## Validation

After Railway redeploys:

1. `https://trading-bot-clean.up.railway.app/paper/self-check`
2. `https://trading-bot-clean.up.railway.app/paper/scanner-v2-theme-confidence-status?symbols=BE,NVTS,STX,NUAI,CRWV,ONDS&force=1`
3. After a normal scanner cycle: `https://trading-bot-clean.up.railway.app/paper/scanner-v2-candidate-lifecycle-trace-status`

Expected lifecycle authority fields:

- `changes_live_authority: false`
- `changes_ml_authority: false`
- `changes_risk_or_sizing: false`
- `changes_thresholds: false`
- `core_universe_mutated: false`
- `places_orders: false`
- `alters_scan_result: false`
