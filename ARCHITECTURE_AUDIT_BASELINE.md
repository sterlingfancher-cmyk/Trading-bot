# Architecture Audit Baseline — August 3, 2026

## Scope

This is the canonical static-refactor baseline for `sterlingfancher-cmyk/Trading-bot`. It inventories architectural debt and protects staged migration contracts. It does not assert that every static finding is an active runtime defect.

Current validated audit:

- GitHub Actions run: `30876010241`
- head commit: `de8d095c60e068988397e23dc0dad3f057e7ea36`
- structural audit: pass
- architecture ownership contract: pass
- typed configuration parity: pass
- Stage B immutable model tests: pass
- StateStore shadow parity: pass
- Stage C StateStore tests: pass
- Stage D shadow comparison tests: pass
- new critical findings: 0
- new warnings: 0

## Current Repository Surface

- Python files: 153
- Python source lines: 69,297
- internal import edges: 173
- import cycles: 0
- module-level calls: 2,460
- import-time thread creations: 2
- persistent watchdog loops: 7
- genuinely high-frequency or potentially busy watchdogs: 1
- dynamic mutation targets: 72
- targets with overlapping mutation owners: 29
- environment keys observed: 867
- conflicting environment defaults: 3
- parameter names observed: 523
- conflicting parameter owners: 10
- route literals: 187
- route overlaps: 5
- exact duplicate function-body groups: 65
- parallel version families: 1
- broad exception handlers that only pass: 482
- provider-like calls inside loops: 1
- critical findings: 29
- warning findings: 90
- informational findings: 114

The absence of import cycles and the passing compile/static gates are positive. The dominant debt remains runtime ownership ambiguity, import-time activation, overlapping callable replacement, duplicated configuration interpretation, and broad exception suppression.

## Highest-Priority Ownership Debt

### Scanner authority

`scan_signals` currently has 14 allowed legacy owners. The target is one canonical `trading.signals.SignalEngine` with explicit, ordered signal layers rather than replacement of the public callable.

### Entry and decision authority

`try_entries_and_rotations` currently has 13 allowed legacy owners. The target is one canonical `trading.decision.DecisionEngine` that emits typed policy effects:

- `HARD_BLOCK`
- `SIZE_REDUCTION`
- `SCORE_ADJUSTMENT`
- `RANKING_PREFERENCE`
- `TELEMETRY_ONLY`

### State authority

`save_state` currently has 16 allowed legacy owners. The target is one canonical `trading.state.StateStore`. No current owner has been removed or replaced yet.

Other high-overlap targets include:

- `entry_quality_check`: 10 owners
- `enter_position`: 9 owners
- `UNIVERSE`: 6 owners
- `BUCKET_CONFIG`: 5 owners
- `apply_aggression_adjustments`: 5 owners
- `manage_exits`: 3 owners
- `download_prices`: 3 owners
- `run_cycle`: 3 owners

## Known Configuration Debt

The typed configuration contract preserves five known conflicts or ambiguities without resolving them:

1. `MIN_ENTRY_SCORE_NEUTRAL`
   - `app.py`: `0.0140`
   - `news_sentiment_engine.py`: `0.033`
2. `STATE_FILE`
   - canonical: `state.json`
   - diagnostic fallbacks also include `None` and an empty string
3. `EOD_ALLOCATION_WINDOW_MINUTES`
   - canonical literal: `45`
   - other owners use dynamic values
4. `MAX_INTRADAY_DRAWDOWN_PCT`
   - account hard risk uses fraction units
   - surge-local limits use percentage points
5. `MAX_DAILY_DRAWDOWN_PCT`
   - percentage-point and dynamically resolved module-local meanings coexist

The typed snapshot is non-authoritative. Any effective value change remains a trading-behavior change and requires backtest, walk-forward or untouched holdout, cost/slippage sensitivity, and forward paper evidence.

## Known Route Debt

Five exact route overlaps remain registered in the ownership contract:

- `/paper/follow-through-review`
- `/paper/live-volatility-status`
- `/paper/next-session-risk-plan`
- `/paper/risk-improvement-status`
- `/paper/volatility-stop-plan`

New route overlaps are blocked. Existing overlaps must be removed through controlled handler migration.

## Performance and Reliability Debt

- `performance_audit_composition_guard.py` still runs a five-second repair loop.
- One provider-like `download_prices` call remains inside a loop in `app.py` and requires profiling/caching review.
- 482 broad `except Exception: pass` paths remain and must be narrowed incrementally.
- `app.py` remains approximately 5,037 lines.
- Heavy V1/V2 historical research has been isolated from the single production web worker. Forward-shadow and read-only status capability remain; historical research must run through an explicit or dedicated research process.

## Completed Migration Foundations

### Stage A — Ownership contracts — Complete

Implemented:

- `architecture_ownership_registry.json`
- `architecture_contract_validation.py`
- ownership validation in `.github/workflows/refactor-audit.yml`

Validated:

- callable targets registered: 10
- route targets registered: 5
- environment targets registered: 3
- ownership violations: 0
- legacy owner removal is allowed and recorded as progress
- new undeclared owners on protected targets are blocked
- new route overlaps and environment-default conflicts are blocked

### Stage B — Typed configuration and immutable shadow models — Complete

Canonical implementation:

- `typed_configuration_contract.json`
- `typed_configuration_snapshot.py`
- `shadow_decision_models.py`
- `test_architecture_stage_b.py`

Validated:

- typed configuration status: pass
- violations: 0
- known conflicts preserved: 5
- canonical defaults present
- immutable signal, market, risk, position, policy, candidate, and cycle models tested
- shadow authority only
- no runtime imports or order methods

A duplicate Stage B parity implementation was removed before promotion, preventing the audit framework itself from creating overlapping ownership.

### Stage C — StateStore shadow parity — Foundation complete

Implemented:

- `state_store_contract.json`
- `state_store_shadow.py`
- `test_state_store_stage_c.py`
- StateStore validation in `.github/workflows/refactor-audit.yml`

Validated current capabilities:

- atomic `os.replace` writes
- file fsync
- directory fsync attempt
- thread locking
- file locking when supported
- shared read and exclusive write paths
- retrying reads
- latest, largest, and prewrite backups
- backup fallback reads
- non-overlapping cycle guard
- canonical `STATE_FILE=state.json` observation

StateStore shadow result: pass, with zero symbol, call, default, capability, or typed-configuration violations.

This is not an authority migration. The shadow validator does not open the production state file, replace `save_state`, or change state paths.

### Stage D — Shadow decision comparison — Foundation complete

Implemented:

- `shadow_decision_comparison_contract.json`
- `shadow_decision_comparison.py`
- `test_shadow_decision_stage_d.py`
- Stage D tests in `.github/workflows/refactor-audit.yml`

Validated behavior:

- two decisions must share the same cycle ID
- both decisions must produce the same immutable input fingerprint
- candidates are compared by symbol and side
- divergences cover presence, allowance, selection, terminal reason, final score, and size multiplier
- comparison results are immutable and marked `comparison_only`
- mismatched cycle or input snapshots are rejected
- no runtime, state, route, broker, or order authority exists
- automatic promotion remains false
- forward evidence minimum remains 30 candidates and 20 one-day outcomes

This foundation is not connected to the production decision path. It records no live cycle yet and cannot place orders.

## Permanent Audit Cadence

### Every Python update or pull request

The consolidated audit runs:

1. repository compile and static safety checks;
2. structural mutation/overlap comparison against the base commit;
3. architecture ownership contract validation;
4. typed configuration parity validation;
5. immutable Stage B model tests;
6. StateStore shadow parity validation;
7. Stage C tests;
8. Stage D shadow comparison tests;
9. artifact publication and commit status.

New critical structural debt, unauthorized protected owners, configuration drift, StateStore safety drift, or shadow comparison authority expansion fails the audit.

### Weekly

A full deep architecture audit runs Sunday at `12:30 UTC` and retains JSON and Markdown reports for 30 days.

### Weekdays after market close

A bounded, concurrent, read-only Railway snapshot runs at `23:15 UTC`, or manually through workflow dispatch. It checks web connectivity, `/paper/self-check`, paper status, V1/V2 research status, persisted ablation, and regime reports. It does not initiate research, execute a trading cycle, mutate state, or place orders.

## Next Controlled Milestone — Runtime Shadow Capture Adapter

The next Stage D milestone is to connect comparison telemetry without adding another wrapper or changing the entry callable:

1. identify one existing, canonical cycle boundary that already has candidates, market, risk, positions, and final decisions;
2. add an explicit observer call at that boundary rather than replacing `scan_signals` or `try_entries_and_rotations`;
3. construct the immutable input snapshot once;
4. translate the current decision into `CycleDecision`;
5. run a read-only candidate evaluator against the same snapshot;
6. call `compare_cycles` and retain bounded telemetry;
7. expose only read-only status through an existing diagnostics registry or a uniquely owned route;
8. preserve trading output byte-for-byte and decision-for-decision;
9. require targeted mocks, startup smoke testing, one successful paper cycle, and `/paper/self-check`;
10. collect at least 30 forward candidates and 20 one-day outcomes before any authority migration.

The adapter must not create a new watchdog, public callable owner, route overlap, state owner, or order path.

## Acceptance Targets

- `scan_signals`: 14 owners toward 1 canonical owner
- `try_entries_and_rotations`: 13 owners toward 1 canonical owner
- `save_state`: 16 owners toward 1 StateStore
- route overlaps: 5 toward 0
- environment conflicts: 3 toward 0
- parameter-owner conflicts: 10 toward explicit namespaced ownership
- critical structural findings: 29 toward 0
- high-frequency watchdogs: 1 toward 0 unless explicitly justified
- no new import cycles
- no increase in broad exception suppression
- no live, ML, state, or order-authority expansion
