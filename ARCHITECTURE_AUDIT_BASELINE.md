# Architecture Audit Baseline — August 3, 2026

## Scope

This is the canonical refactor baseline for `sterlingfancher-cmyk/Trading-bot`. It inventories architectural debt and protects staged migration contracts. It does not assert that every static finding is an active runtime defect.

Latest fully validated repository/startup run:

- GitHub Actions run: `30877811708`
- head commit: `58da8e70559a6dd33fa596d13ecdc157c57d4287`
- repository validation: pass
- structural audit: pass
- architecture ownership contract: pass
- typed configuration parity: pass
- Stage B immutable model tests: pass
- StateStore shadow parity: pass
- Stage C StateStore tests: pass
- Stage D decision-comparison tests: pass
- Stage D runtime-capture tests: pass
- declared dependency installation: pass
- exact Gunicorn startup smoke: pass
- new critical findings: 0
- new warnings: 0

The startup smoke used the repository’s real Gunicorn target. `/bootstrap-status` became reachable, the complete application reached `ready` in approximately 14 seconds, runtime worker registration passed, and `/` rendered successfully.

## Current Repository Surface

- Python files: 159
- Python source lines: 70,671
- internal import edges: 183
- import cycles: 0
- module-level calls: 2,489
- import-time thread creations: 2
- persistent watchdog loops: 7
- genuinely high-frequency or potentially busy watchdogs: 1
- dynamic mutation targets: 72
- targets with overlapping mutation owners: 29
- environment keys observed: 869
- conflicting environment defaults: 3
- parameter names observed: 523
- conflicting parameter owners: 10
- route literals: 187
- route overlaps: 5
- exact duplicate function-body groups: 65
- parallel version families: 2
- broad exception handlers that only pass: 482
- provider-like calls inside loops: 1
- critical findings: 29
- warning findings: 90
- informational findings: 116

The absence of import cycles and the passing compile, ownership, configuration, state, shadow, and startup gates are positive. The dominant debt remains runtime ownership ambiguity, import-time activation, overlapping callable replacement, duplicated configuration interpretation, and broad exception suppression.

## Highest-Priority Ownership Debt

### Scanner authority

`scan_signals` has 14 allowed legacy owners. The target is one canonical `trading.signals.SignalEngine` with explicit ordered layers rather than public-callable replacement.

### Entry and decision authority

`try_entries_and_rotations` has 13 allowed legacy owners. The target is one canonical `trading.decision.DecisionEngine` that emits typed policy effects:

- `HARD_BLOCK`
- `SIZE_REDUCTION`
- `SCORE_ADJUSTMENT`
- `RANKING_PREFERENCE`
- `TELEMETRY_ONLY`

### State authority

`save_state` has 16 allowed legacy owners. The target is one canonical `trading.state.StateStore`. No current owner has been removed or replaced yet.

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

The typed configuration contract preserves known conflicts or ambiguities without resolving them:

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

Five exact route overlaps remain registered:

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
- Heavy V1/V2 historical research is isolated from the production web worker.
- The public Railway domain currently times out even though the same repository command passes exact local Gunicorn startup and Railway deployment health checks. This is classified as a Railway domain/service-routing incident until the domain attachment is verified.

## Completed Migration Foundations

### Stage A — Ownership contracts — Complete

Implemented:

- `architecture_ownership_registry.json`
- `architecture_contract_validation.py`
- ownership validation in `.github/workflows/refactor-audit.yml`

Validated:

- protected callable targets: 10
- protected route targets: 5
- protected environment targets: 3
- ownership violations: 0
- removal of legacy owners is allowed and recorded as progress
- undeclared new owners, route overlaps, and environment-default conflicts are blocked

### Stage B — Typed configuration and immutable models — Complete

Canonical implementation:

- `typed_configuration_contract.json`
- `typed_configuration_snapshot.py`
- `shadow_decision_models.py`
- `test_architecture_stage_b.py`

Validated:

- typed configuration status: pass
- violations: 0
- known conflicts preserved
- canonical defaults present
- immutable signal, market, risk, position, policy, candidate, and cycle models tested
- shadow authority only
- no runtime imports or order methods

### Stage C — StateStore shadow parity — Foundation complete

Implemented:

- `state_store_contract.json`
- `state_store_shadow.py`
- `test_state_store_stage_c.py`

Validated current capabilities:

- atomic `os.replace` writes
- file and directory fsync
- thread and supported file locking
- shared read and exclusive write paths
- retrying reads
- latest, largest, and prewrite backups
- backup fallback reads
- non-overlapping cycle guard
- canonical `STATE_FILE=state.json`

StateStore shadow result is pass with zero symbol, call, default, capability, or typed-configuration violations. It does not open the production state file, replace `save_state`, or change state paths.

### Stage D1 — Pure decision comparison — Complete

Implemented:

- `shadow_decision_comparison_contract.json`
- `shadow_decision_comparison.py`
- `test_shadow_decision_stage_d.py`

Validated:

- matching cycle ID and identical input fingerprint are required
- candidates are compared by symbol and side
- divergences cover presence, allowance, selection, terminal reason, score, and size multiplier
- results are immutable and `comparison_only`
- no runtime, state, route, broker, or order authority
- automatic promotion remains false

### Stage D2 — Runtime capture-parity adapter — Implemented and repository-validated

Implemented:

- `runtime_shadow_capture_contract.json`
- `runtime_shadow_capture.py`
- `test_runtime_shadow_capture.py`
- existing `run_report_guard.py` owner extended with one observer call
- `/paper/self-check` v6 includes `runtime_shadow_capture` as component six

Safety boundary:

- no new `run_cycle`, scanner, or entry callable owner
- no new wrapper, watchdog, or route
- observer runs only after the existing cycle returns
- returned trading result does not contain the shadow payload
- bounded telemetry is retained under `portfolio["shadow_decision_comparison"]`
- adapter does not call `save_state`, providers, brokers, or order methods
- current and shadow decisions are intentionally identical in V1 to prove translation and comparison plumbing
- independent shadow policy is false
- capture-parity samples do not count toward forward promotion evidence

Validation:

- parity translation tests: pass
- bounded history and duplicate-cycle tests: pass
- skipped-cycle handling: pass
- production result-preservation test: pass
- AST authority boundary test: pass
- exact Gunicorn startup smoke: pass

Runtime capture after a real market cycle remains unverified through the public domain because the domain is not responding.

## Listener-First Startup and Research Isolation

Canonical deployment command is pinned in both `Procfile` and `railway.json`:

`DEFERRED_WSGI_BOOTSTRAP=true PYTHONPATH=bootstrap:. gunicorn bootstrap_wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`

Railway health check:

- path: `/bootstrap-status`
- timeout: 120 seconds

Startup protections:

- V1 and V2 automatic historical research disabled before WSGI import
- heavy research not resumed inside the web worker
- lightweight bootstrap WSGI callable constructed before the legacy loader starts
- legacy loading starts through a bounded delayed timer, default 1 second
- root and `/bootstrap-status` can respond while the full application loads
- exact CI startup reached ready in approximately 14 seconds

These changes affect process placement and availability only; trading decisions are unchanged.

## Permanent Audit Cadence

### Every Python update or pull request

The consolidated audit runs:

1. repository compile and static safety checks;
2. structural mutation/overlap comparison;
3. architecture ownership validation;
4. typed configuration parity;
5. Stage B immutable-model tests;
6. StateStore parity and Stage C tests;
7. Stage D comparison tests;
8. runtime capture tests;
9. declared dependency installation;
10. exact Gunicorn startup smoke;
11. artifact publication and commit status.

New critical debt, unauthorized owners, configuration drift, StateStore safety drift, shadow-authority expansion, or startup failure fails the audit.

### Weekly

A full deep architecture audit runs Sunday at `12:30 UTC` and retains reports for 30 days.

### Post-push and weekdays after market close

A bounded, concurrent, read-only Railway snapshot probes:

- `/bootstrap-status`
- `/`
- `/paper/status`
- `/paper/self-check`
- V1/V2 research status
- persisted V2 ablation and regime reports

The snapshot distinguishes listener availability from full-application readiness. It does not initiate research, execute a cycle, mutate state, or place orders.

## Current External Availability Incident

Evidence:

- exact repository Gunicorn startup: pass
- application registration: pass
- root rendering locally: pass
- Railway deployment checks: success
- Railway-configured health check: `/bootstrap-status`
- public domain post-deploy probes: 0 of 8 endpoints reachable; each timed out waiting for response

Most likely next external check:

- confirm which Railway service owns `trading-bot-clean.up.railway.app`
- two Railway services currently publish deployment statuses from this repository
- verify that the domain is attached to the service using `railway.json` and the latest commit
- remove or detach any stale duplicate domain/service mapping

Do not change strategy or add more runtime wrappers to address this routing incident.

## Next Controlled Milestone

1. Resolve or verify the Railway public-domain attachment.
2. Run `/paper/self-check` and confirm:
   - version `fast-self-check-override-2026-08-03-v6-shadow-capture`
   - six components
   - runtime capture `awaiting_first_market_cycle` or captured parity
3. Observe one successful market cycle with unchanged trading output.
4. Only then add an independent read-only candidate evaluator to the same observer path.
5. Collect at least 30 independent forward candidates and 20 one-day outcomes before considering authority migration.

## Acceptance Targets

- `scan_signals`: 14 owners toward 1
- `try_entries_and_rotations`: 13 owners toward 1
- `save_state`: 16 owners toward 1
- route overlaps: 5 toward 0
- environment conflicts: 3 toward 0
- parameter-owner conflicts: 10 toward namespaced ownership
- critical structural findings: 29 toward 0
- high-frequency watchdogs: 1 toward 0 unless justified
- no new import cycles
- no increase in broad exception suppression
- no live, ML, state, or order-authority expansion
