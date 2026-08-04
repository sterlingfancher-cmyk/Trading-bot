# Architecture Audit Baseline — August 3, 2026

## Scope

This document records the first calibrated, repository-wide refactor audit. It is a static architecture baseline, not a claim that every finding is an active runtime defect.

Source run:

- GitHub Actions run: `30874076617`
- head commit: `37f1e4a170868720ec723724b1e3a142d9f8bedc`
- audit version: `refactor-audit-cli-2026-08-03-v3-bounded-loop-calibration`
- result: pass
- new critical findings versus base: 0
- new warnings versus base: 0

The per-update gate passed because the audit changes did not introduce new structural debt. Existing debt is preserved below as the controlled refactor backlog.

## Repository Surface

- Python files: 145
- Python source lines: 67,643
- internal import edges: 170
- import cycles: 0
- module-level calls: 2,442
- import-time thread creations: 2
- persistent watchdog loops: 7
- bounded `while True` loops excluded from watchdog debt: 1
- genuinely high-frequency or potentially busy watchdogs: 1
- dynamic mutation targets: 72
- targets with overlapping mutation owners: 29
- environment keys observed: 866
- conflicting environment defaults: 3
- parameter names observed: 523
- conflicting parameter owners: 10
- route literals: 187
- route overlaps: 5
- exact duplicate function-body groups: 64
- parallel version families: 1
- broad exception handlers that only pass: 482
- provider-like calls inside loops: 1
- critical findings: 29
- warning findings: 90
- informational findings: 113

## Interpretation

The architecture has no detected static import cycle, and all tracked Python files passed the repository compile and safety gate.

The dominant risk is runtime ownership ambiguity:

- multiple modules replace the same public scanner and entry callables;
- state, entry quality, execution, and route functions have multiple owners;
- some configuration names carry different defaults or percentage units;
- many modules activate behavior at import time and suppress exceptions.

The correct response is not mass deletion. The system requires a staged migration to declared interfaces and one authoritative owner per critical responsibility.

## Priority 1 — Critical Callable Ownership

### Scanner authority

`scan_signals` is replaced from 14 modules:

- `breakout_participation_layer.py`
- `breakout_scanner_ownership_guard.py`
- `dynamic_universe_builder.py`
- `fvg_runtime.py`
- `loss_streak_defensive_governor.py`
- `market_participation_accelerator.py`
- `multi_timeframe_swing.py`
- `opening_surge_participation.py`
- `pattern_recognition_layer.py`
- `relative_strength_leader_exception.py`
- `scanner_runtime_contract.py`
- `scanner_stack_emergency_reset.py`
- `scanner_v2_candidate_lifecycle_trace.py`
- `shared_cycle_identity.py`

Target architecture:

- one canonical `SignalEngine` or scanner service owns the public scanner callable;
- strategy layers implement explicit, ordered interfaces rather than replacing the public function;
- ownership, ordering, and telemetry are data contracts rather than watchdog repairs.

### Entry authority

`try_entries_and_rotations` is replaced from 13 modules:

- `bear_recovery_stack_contract.py`
- `bear_soft_pause_short_recovery.py`
- `core_entry_pipeline.py`
- `entry_pipeline_composition_guard.py`
- `entry_pipeline_xray.py`
- `entry_pipeline_xray_bear_ownership_guard.py`
- `paper_exposure_rotation.py`
- `performance_risk_activation_guard.py`
- `performance_risk_calibration.py`
- `post_harvest_entry_fallback.py`
- `post_harvest_redeployment_controller.py`
- `profit_maturity_rotation_layer.py`
- `theme_starter_exception.py`

Target architecture:

- one canonical `DecisionEngine` owns candidate ranking, permission checks, selection, and rotation decisions;
- risk policies return typed decisions such as `HARD_BLOCK`, `SIZE_REDUCTION`, `SCORE_ADJUSTMENT`, or `RANKING_PREFERENCE`;
- recovery, X-Ray, and diagnostics observe the decision path without wrapping or replacing it.

### Other high-overlap targets

- `save_state`: 16 modules
- `entry_quality_check`: 10 modules
- `enter_position`: 9 modules
- `UNIVERSE`: 6 modules
- `BUCKET_CONFIG`: 5 modules
- `apply_aggression_adjustments`: 5 modules
- `portfolio`: 4 modules
- `feedback_loop_status`: 4 modules
- `download_prices`: 3 modules
- `manage_exits`: 3 modules
- `market_status`: 3 modules
- `rotation_allowed`: 3 modules
- `run_cycle`: 3 modules

These targets require declared owners before code is removed.

## Priority 2 — Configuration and Unit Ownership

### Neutral entry-score conflict

`MIN_ENTRY_SCORE_NEUTRAL` has two different fallbacks:

- `app.py`: `0.0140`
- `news_sentiment_engine.py`: `0.033`

This is a genuine namespace/default conflict. The news engine should consume the canonical runtime score helper or a separately named advisory fallback. Because changing the fallback can affect candidate interpretation, the eventual repair must be treated as a trading-behavior change and receive backtest and forward validation.

### State-file ownership conflict

`STATE_FILE` is read with multiple fallback conventions:

- most modules use `state.json`;
- `state_provenance_monitor.py` permits `None`;
- `state_size_watchdog.py` permits an empty string.

Target architecture:

- one `StateStore` resolves the path and persistence mode;
- diagnostics consume the resolved store descriptor instead of independently interpreting environment variables.

### Drawdown-unit ambiguity

The codebase uses both decimal fractions and displayed percentage points.

Examples:

- central runtime hard drawdown: `0.025`, meaning 2.5%;
- surge executor constants: `1.50`, compared with fields named `*_pct`.

The surge values may be internally consistent, but identical suffixes do not guarantee identical units.

Target architecture:

- use explicit names such as `*_FRACTION` and `*_PCT_POINTS`;
- centralize conversion at the boundary;
- include units in typed risk snapshots and tests.

### Other parameter-owner conflicts

- `EOD_ALLOCATION_WINDOW_MINUTES`
- `MAX_DAILY_DRAWDOWN_PCT`
- `MAX_INTRADAY_DRAWDOWN_PCT`
- `MAX_ROWS`
- `MAX_SYMBOLS`
- `MIN_AVG_VOLUME`
- `MIN_DOLLAR_VOLUME`
- `MIN_PRICE`
- `WATCHDOG_FAST_ITERATIONS`
- `WATCHDOG_MAX_ITERATIONS`
- `WATCHDOG_SECONDS`

Not every repeated name is incorrect. The refactor must distinguish global policy, module-local limits, diagnostics, and research settings through namespaces and typed configuration objects.

## Priority 3 — Route and Runtime Ownership

Five exact route overlaps were found:

- `/paper/follow-through-review`
- `/paper/live-volatility-status`
- `/paper/next-session-risk-plan`
- `/paper/risk-improvement-status`
- `/paper/volatility-stop-plan`

The overlapping owners are concentrated in:

- `risk_bootstrap.py`
- `risk_improvements.py`
- `live_volatility.py`

Target architecture:

- one route registry declares endpoint ownership;
- modules provide handlers, not opportunistic registration;
- duplicate routes fail a startup test before Railway deployment.

## Priority 4 — Performance and Reliability Debt

### High-frequency watchdog

`performance_audit_composition_guard.py` calls its installer every five seconds.

The performance audit is advisory research. Its composition check should become event-driven, startup-driven, or substantially lower frequency unless evidence shows a five-second repair loop is necessary.

### Provider work inside a loop

The audit found one provider-like call inside a loop in `app.py`: `download_prices`.

This requires profiling and caching review. It is not automatically a bug, but repeated provider work can increase latency, timeout risk, and data inconsistency within one cycle.

### Broad exception suppression

The repository contains 482 broad exception handlers whose bodies only pass.

This creates blind spots. Refactoring should replace them incrementally with:

- bounded exception classes;
- structured telemetry;
- explicit fallback status;
- tests proving the fallback behavior.

Do not replace all handlers mechanically. Some startup and diagnostic paths intentionally degrade gracefully.

### Module size

Largest modules include:

- `app.py`: 5,037 lines, 158 functions
- `market_surge_deployment_mode.py`: 1,434 lines
- `performance_audit_lab.py`: 1,384 lines
- `performance_audit_lab_v2.py`: 1,297 lines
- `opening_surge_participation.py`: 924 lines
- `dynamic_universe_builder.py`: 898 lines
- `core_entry_pipeline.py`: 789 lines
- `neutral_momentum_starter_extension.py`: 785 lines

Line count is not the primary target. The target is explicit ownership and deterministic execution.

## Priority 5 — Duplicate and Parallel Implementations

- exact duplicate function-body groups: 64
- parallel version family: `performance_audit_lab.py` and `performance_audit_lab_v2.py`

These findings require semantic review. Exact helper duplication can move into utilities; versioned research modules can remain separate until V2 is validated and V1 consumers are migrated.

## Migration Sequence

### Stage A — Ownership contracts

1. Create a machine-readable ownership registry for:
   - scanner;
   - decision/entry;
   - execution;
   - exit management;
   - risk policy;
   - state storage;
   - market data;
   - route registration.
2. Record current owners and target canonical owner.
3. Make new unauthorized owners fail the structural audit.
4. Do not change runtime authority in this stage.

### Stage B — Typed configuration

1. Introduce namespaced configuration models.
2. Add explicit fraction-versus-percentage units.
3. Resolve duplicate environment defaults.
4. Preserve current effective runtime values.
5. Add snapshot tests proving no policy drift.

### Stage C — State service

1. Introduce one `StateStore` interface.
2. Put path, locking, atomic write, backup, and provenance behind that interface.
3. Route existing callers through an adapter.
4. Compare state output before and after migration.
5. Remove direct `save_state` replacements only after parity tests pass.

### Stage D — Shadow decision engine

1. Define immutable signal, market, risk, position, and decision models.
2. Run the current entry path and new decision engine against the same cycle snapshot.
3. Record:
   - selected symbols;
   - rejected symbols;
   - terminal reasons;
   - position sizes;
   - risk and exposure;
   - execution eligibility.
4. New engine remains read-only and places no orders.
5. Collect at least 30 forward candidates and 20 one-day outcomes.

### Stage E — Controlled authority migration

1. Migrate scanner ownership first.
2. Migrate entry/decision ownership second.
3. Migrate state ownership third.
4. Remove wrappers and watchdogs in small batches.
5. Require repository validation, structural audit, unit tests, backtest, walk-forward, and forward paper evidence for every behavior-affecting batch.

## Acceptance Targets

The refactor should move toward:

- `scan_signals`: 14 owners to 1 canonical owner with declared composable layers;
- `try_entries_and_rotations`: 13 owners to 1 canonical decision engine;
- `save_state`: 16 owners to 1 state service;
- route overlaps: 5 to 0;
- environment conflicts: 3 to 0;
- parameter-owner conflicts: 10 to explicit namespaced ownership;
- critical structural findings: 29 toward 0;
- genuinely high-frequency watchdogs: 1 to 0 unless explicitly justified;
- no increase in broad exception suppression;
- no new import cycles;
- no new live or ML authority.

## Immediate Next Implementation

The next code milestone is a read-only ownership registry and contract validator. It must describe existing and target ownership without replacing current callables. After that, the first shadow decision models and comparison recorder can be introduced without order authority.
