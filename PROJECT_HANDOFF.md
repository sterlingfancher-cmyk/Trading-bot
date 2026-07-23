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

This is treated as a state provenance/persistence consistency defect, not a trading-strategy signal. Possible causes include an older state snapshot, a different state path, backup fallback, worker-local memory divergence, or recalculation from a different source contract.

## Runtime Reliability v3

Version: `market-data-resilience-2026-07-22-v1`

Route: `/paper/provider-health-status`

The guard bounds yfinance requests, records per-symbol latency/outcomes, opens a short circuit after repeated failures, and preserves the legacy unavailable-data contract. It does not alter strategy, thresholds, sizing, risk, orders, executable universe, ML authority, or live authority.

## Cycle Alignment v2

Version: `cycle-alignment-overlay-2026-07-23-v1`

Route: `/paper/cycle-alignment-status`

The afternoon test confirms the cycle-alignment milestone is working. Decision and blocker producers now report the same cycle, and same-cycle count comparison is active.

## State Provenance and Monotonicity Monitor

Version: `state-provenance-monitor-2026-07-23-v1`

Route: `/paper/state-provenance-status`

The monitor:

- wraps `load_state` passively and returns the original state unchanged;
- records state revision, state update timestamp/source, persistence mode, file path, file size, modification time, and a short SHA-256 identity;
- records execution rows, wins, losses, realized total, equity, and position count;
- maintains persistent high-water marks in a separate sidecar file beside the state file;
- flags backward movement in revision, execution rows, wins, losses, or realized total;
- reports whether the latest read appears to come from the primary state file or a backup fallback based on state I/O telemetry;
- never restores, overwrites, merges, or modifies trading state;
- does not change positions, signals, risk, sizing, orders, ML authority, or live authority.

The sidecar file is `state_provenance_status.json` in the active state directory. It is diagnostic only and is not used as a trading-state source.

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
  - `966a10e42c283f63e99e28c0c538137aa13cdc57`
- `usercustomize.py`
  - state provenance registration: `28a0d407638e9e7451d8c004036b8752820f4959`
- `PROJECT_HANDOFF.md`
  - this commit documents the afternoon regression evidence and validation contract.

## Validation After Merge and Railway Redeploy

Run:

1. `https://trading-bot-clean.up.railway.app/paper/self-check`
2. `https://trading-bot-clean.up.railway.app/paper/state-provenance-status`
3. `https://trading-bot-clean.up.railway.app/paper/state-transaction-status`
4. `https://trading-bot-clean.up.railway.app/paper/cycle-alignment-status`
5. `https://trading-bot-clean.up.railway.app/paper/provider-health-status`

Expected provenance fields:

- `version: state-provenance-monitor-2026-07-23-v1`
- `current.metrics.state_revision`
- `current.metrics.execution_rows`
- `current.metrics.wins_total`
- `current.metrics.losses_total`
- `current.metrics.realized_total`
- `current.state_file.path`
- `current.state_file.sha256_prefix`
- `current.source_hint.source`
- `current.persistence_mode`
- `high_water_marks`
- `regression_detected`
- `regressions`
- all authority fields false

The first observation establishes a deployment-local high-water baseline. Subsequent observations should reveal whether cumulative metrics regress again and whether the file identity, revision, state path, or source hint changes at the same time.

Use `/paper/full-self-check` only for a failed routine check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Next Steps

1. Merge the state provenance branch after diff review.
2. Validate the provenance and transaction routes after Railway redeploy.
3. Capture at least two observations around a normal paper cycle.
4. If a regression is detected, compare revision, state path, file hash, source hint, and backup event before considering any restoration behavior.
5. Do not automatically restore or merge state until the precise source of divergence is proven.
6. Resume the remaining single missing blocker-reason attribution after state consistency is understood.

No filter should be relaxed solely because a stock finished strongly.
