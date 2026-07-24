# Automated Trading Project Handoff — Updated July 24, 2026

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

## July 23 Baselines

The July 23 morning compact self-check passed with equity `10970.12`, realized total `970.14`, 88 execution rows, 36 wins, 18 losses, zero open positions, stable recursion-safe entry composition, no current pipeline error, and 54 matching decision/blocker signals.

The afternoon compact self-check generated at `2026-07-23 18:30:47` also passed, with matching same-cycle decision and blocker counts, but cumulative append-only counters moved backward:

- execution rows: `88 -> 83`
- wins: `36 -> 34`
- losses: `18 -> 17`

Net realized P&L also changed, but it is contextual rather than monotonic because legitimate losing exits can reduce it.

## July 24 Morning Validation

The compact self-check generated at `2026-07-24 15:19:30` passed:

- equity: `10954.26`
- cash: `10954.26`
- open positions: `0`
- realized today: `100.25`
- realized total: `954.28`
- execution rows: `85`
- wins/losses: `35 / 18`
- entry pipeline stable and recursion-safe
- no required-path failures or warnings
- decision/blocker cycle ID: `cycle-20260724T151539135164Z-93656e7c`
- same-cycle comparison: `true`
- count difference: `0`
- source mismatch: `false`
- blocker reason coverage: `96.55%`
- missing reason rows: `1`
- ML remains advisory-only with no live authority

The compact test passed, so `/paper/full-self-check` was not warranted.

## Runtime Reliability v3

Version: `market-data-resilience-2026-07-22-v1`

Route: `/paper/provider-health-status`

The guard bounds yfinance requests, records per-symbol latency/outcomes, opens a short circuit after repeated failures, and preserves the legacy unavailable-data contract. It does not alter strategy, thresholds, sizing, risk, orders, executable universe, ML authority, or live authority.

## Cycle Alignment v2

Version: `cycle-alignment-overlay-2026-07-23-v1`

Route: `/paper/cycle-alignment-status`

Decision and blocker producers report the same cycle, and same-cycle count comparison is active.

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
- exposes sidecar persistence failures as warnings;
- maintains persistent high-water marks in a separate diagnostic sidecar;
- never restores, overwrites, merges, or modifies trading state.

The sidecar file remains `state_provenance_status.json` in the active state directory. It is diagnostic only and is not used as a trading-state source.

## Missing Blocker-Reason Trace v1

Version: `missing-reason-trace-2026-07-24-v1`

Route: `/paper/missing-reason-trace-status`

The trace overlay addresses the remaining single missing blocker-reason row without fabricating a reason. It:

- reads the existing blocked-entry reason audit;
- exposes a bounded sample containing symbol, source, source key, placeholder, and category;
- adds `missing_reason_symbols`, `missing_reason_sample`, and `missing_reason_trace_version` to the compact scanner section;
- identifies which producer contract omitted terminal reason detail;
- does not alter scanner results, blocker decisions, thresholds, filters, risk, sizing, orders, executable universe, ML authority, or live authority.

The next routine compact test should identify the exact source of the remaining placeholder. Repair the producer contract only after that evidence is visible; do not infer or synthesize a trading reason.

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
- no mutation of account history or current positions;
- no fabricated blocker attribution.

## Files and Commits

- `state_provenance_monitor.py`
  - v2 branch commit: `9ce6ddc4e03c38a7c9c4f5e103c2fbbad7f0892b`
- `missing_reason_trace_overlay.py`
  - initial trace overlay: `f42f4c985a7f1a7695c6cafdc46584ab379a63d8`
- `usercustomize.py`
  - missing-reason trace registration: `e0cbdd54775e2e6f17ced686b4e31e3f619d159f`
- `PROJECT_HANDOFF.md`
  - updated in the same branch with July 24 runtime evidence and the trace validation contract.

## Validation Status

- Source branch: `agent/state-provenance-v2`
- Base commit: `cd42d0d6637ccb79a2f795140eb5b805a5a7b38b`
- Morning deployed `/paper/self-check`: passed
- `/paper/full-self-check`: not used because the compact check passed without missing critical fields, required-path failures, runtime errors, or warnings
- Source-level safety review: trace overlay is read-only and bounded
- Deployment validation for the new branch changes remains pending merge and Railway redeploy

## Validation After Merge and Railway Redeploy

Run in this order:

1. `https://trading-bot-clean.up.railway.app/paper/self-check`
2. `https://trading-bot-clean.up.railway.app/paper/state-provenance-status`
3. `https://trading-bot-clean.up.railway.app/paper/missing-reason-trace-status`
4. `https://trading-bot-clean.up.railway.app/paper/state-transaction-status`
5. `https://trading-bot-clean.up.railway.app/paper/cycle-alignment-status`
6. `https://trading-bot-clean.up.railway.app/paper/provider-health-status`

Expected compact scanner fields:

- `missing_reason_rows`
- `missing_reason_symbols`
- `missing_reason_sample`
- `missing_reason_trace_version: missing-reason-trace-2026-07-24-v1`

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

Use `/paper/full-self-check` only for a failed routine check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Next Steps

1. Review and merge draft PR #6.
2. Validate `/paper/self-check` first after Railway redeploy.
3. Capture the new `missing_reason_sample` and repair only the identified diagnostic producer contract.
4. Capture at least two state-provenance observations around a normal paper cycle.
5. If an append-only counter regresses, compare revision, state path, file hash, source hint, transaction status, and backup event before considering restoration behavior.
6. Do not automatically restore or merge state until the precise source of divergence is proven.

No filter should be relaxed solely because a stock finished strongly.
