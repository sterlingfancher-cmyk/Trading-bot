# Automated Trading Project Handoff — Updated July 23, 2026

## Standing Rule

Every code or configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Autonomous Engineering Workflow

Continue sequential diagnostic, observability, reliability, documentation, and advisory-only milestones without waiting for approval after each successful validation. Pause for approval before changing executable-universe membership, scanner or signal results, entry/exit logic, thresholds, risk controls, position sizing, order placement, ML decision authority, live-trading authority, or a material architecture decision with multiple reasonable behavioral outcomes.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `/paper/self-check`
- Full diagnostics: `/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## July 23 Morning Baseline

The morning compact self-check passed with equity `10970.12`, realized total `970.14`, 88 execution rows, 36 wins, 18 losses, zero open positions, stable recursion-safe entry composition, no current pipeline error, and 54 matching decision/blocker signals. Cycle IDs were missing at that time.

## July 23 Afternoon Baseline

The afternoon compact self-check generated at `2026-07-23 18:30:47` passed with:

- equity: `11005.46`
- cash: `9812.33`
- open positions: `DELL`, `SNDK`
- unrealized P&L: `151.44`
- realized today: `-3.65`
- realized total: `854.03`
- execution rows: `83`
- wins/losses: `34 / 17`
- stable, recursion-safe entry pipeline
- no required-path failures or warnings
- ML advisory-only, no live authority

Cycle alignment was successfully validated:

- matching decision/blocker ID: `cycle-20260723T182756095055Z-1b50f934`
- `same_cycle_comparison: true`
- `snapshot_alignment: same_cycle`
- `count_difference: 0`
- `source_mismatch: false`

However, cumulative account metrics moved backward from the morning snapshot:

- execution rows: `88 -> 83`
- wins: `36 -> 34`
- losses: `18 -> 17`
- realized total: `970.14 -> 854.03`

The execution-row and outcome-counter decreases remain state provenance/persistence consistency evidence. Net realized P&L is now treated as contextual rather than monotonic because legitimate losing exits can reduce it.

## Runtime Reliability v3

Version: `market-data-resilience-2026-07-22-v1`

Route: `/paper/provider-health-status`

The guard bounds yfinance requests, records per-symbol latency/outcomes, opens a short circuit after repeated failures, and preserves the legacy unavailable-data contract. It does not alter strategy, thresholds, sizing, risk, orders, executable universe, ML authority, or live authority.

## Cycle Alignment v2

Version: `cycle-alignment-overlay-2026-07-23-v1`

Route: `/paper/cycle-alignment-status`

The afternoon test confirms the cycle-alignment milestone is working. Decision and blocker producers now report the same cycle, and same-cycle count comparison is active.

## State Provenance and Monotonicity Monitor v2

Version: `state-provenance-monitor-2026-07-23-v2`

Route: `/paper/state-provenance-status`

The v2 monitor:

- wraps `load_state` passively and returns the original state unchanged;
- treats only state revision, execution rows, wins, and losses as monotonic counters;
- records realized total, equity, and position count as context-only metrics;
- reports deltas from the previous observation;
- reports state-file hash and path changes between observations;
- serializes sidecar read/compute/write operations under a re-entrant lock;
- uses process- and thread-specific temporary files for atomic sidecar replacement;
- exposes sidecar persistence failures as warnings instead of silently reporting success;
- maintains persistent high-water marks in a separate diagnostic sidecar;
- never restores, overwrites, merges, or modifies trading state.

The sidecar file remains `state_provenance_status.json` in the active state directory. It is diagnostic only and is not used as a trading-state source.

## Safety and Authority Boundary

Current work preserves:

- no live authority;
- no ML execution authority;
- no order placement;
- no threshold changes;
- no sizing or risk-control changes;
- no executable-universe mutation;
- no scanner-result modification;
- no automatic state restoration;
- no mutation of account history or current positions.

## Files and Commits

- `market_data_resilience.py`
  - `b3f9d86bdceb23b43bcaf3817bc5634582abfb4b`
- `cycle_alignment_overlay.py`
  - `a95fab9d449723e13270ec3b4d53d2b164fb8360`
- `state_provenance_monitor.py`
  - v1: `966a10e42c283f63e99e28c0c538137aa13cdc57`
  - v2 branch commit: `9ce6ddc4e03c38a7c9c4f5e103c2fbbad7f0892b`
- `usercustomize.py`
  - state provenance registration: `28a0d407638e9e7451d8c004036b8752820f4959`
- `PROJECT_HANDOFF.md`
  - updated in the same branch to document v2 semantics, validation, and safety impact.

## Validation Status

- Source branch: `agent/state-provenance-v2`
- Base commit: `cd42d0d6637ccb79a2f795140eb5b805a5a7b38b`
- Python syntax validation: passed for `state_provenance_monitor.py`
- Deployment validation: not completed because the Railway hostname could not be resolved from the execution environment during this work session.
- `/paper/full-self-check` was not used because no deployed compact self-check result was available to justify escalation.

## Validation After Merge and Railway Redeploy

Run:

1. `https://trading-bot-clean.up.railway.app/paper/self-check`
2. `https://trading-bot-clean.up.railway.app/paper/state-provenance-status`
3. `https://trading-bot-clean.up.railway.app/paper/state-transaction-status`
4. `https://trading-bot-clean.up.railway.app/paper/cycle-alignment-status`
5. `https://trading-bot-clean.up.railway.app/paper/provider-health-status`

Expected provenance fields:

- `version: state-provenance-monitor-2026-07-23-v2`
- `current.metrics.state_revision`
- `current.metrics.execution_rows`
- `current.metrics.wins_total`
- `current.metrics.losses_total`
- `current.metrics.realized_total`
- `current.metric_deltas_from_previous`
- `current.state_file.path`
- `current.state_file.sha256_prefix`
- `current.state_file_identity_changed`
- `current.state_file_path_changed`
- `current.source_hint.source`
- `current.persistence_mode`
- `high_water_marks`
- `monotonic_fields`
- `context_only_fields`
- `sidecar_persistence.ok`
- `regression_detected`
- `regressions`
- all authority fields false

The first observation establishes a deployment-local high-water baseline. Subsequent observations should reveal whether append-only counters regress and whether file identity, revision, state path, source hint, or sidecar persistence changes at the same time.

Use `/paper/full-self-check` only for a failed routine check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Next Steps

1. Review and merge the v2 diagnostic branch.
2. Validate `/paper/self-check` first after Railway redeploy.
3. Validate the provenance route and capture at least two observations around a normal paper cycle.
4. If an append-only counter regresses, compare revision, state path, file hash, source hint, transaction status, and backup event before considering restoration behavior.
5. Do not automatically restore or merge state until the precise source of divergence is proven.
6. Resume the remaining single missing blocker-reason attribution after state consistency is understood.

No filter should be relaxed solely because a stock finished strongly.
