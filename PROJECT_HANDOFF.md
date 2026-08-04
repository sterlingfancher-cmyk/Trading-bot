# Automated Trading Project Handoff — Canonical Status, August 4, 2026

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Public URL: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: advisory only
- Hard-risk ladder unchanged:
  - 1.00% soft realized-loss pause
  - 2.50% hard realized-loss halt
  - 2.50% hard intraday-drawdown halt
  - 3.00% absolute daily-loss ceiling

No audit, refactor, startup, or research-isolation change in this milestone altered signal formulas, entry floors, position sizing, risk limits, existing paper positions, or order authority.

## Latest Account Evidence

The latest user-supplied account snapshot remains the historical `2026-08-03 12:12:53 CDT` observation:

- equity: `$10,738.02`
- cash: `$10,240.9964`
- open paper position: `DELL`
- unrealized P&L: `+$3.22`
- realized lifetime: `+$734.82`
- wins/losses: 35/17
- scanner signals: 41
- no halt, self-defense condition, or active recursion

The public Railway listener is currently unreachable, so no newer production account state is claimed.

## Continuous Validation Policy

### Trading-behavior changes

A change that can affect signals, rankings, scores, entries, exits, sizing, exposure, capacity, or risk is incomplete until it passes:

1. repository/static validation;
2. targeted unit and invariant tests;
3. baseline-versus-candidate backtest;
4. walk-forward or untouched holdout testing;
5. transaction-cost and slippage sensitivity;
6. regime and calendar segmentation;
7. ablation when multiple controls change;
8. forward shadow or bounded paper canary;
9. post-deploy `/paper/self-check`.

### Non-behavior changes

Documentation, audit tooling, read-only telemetry, and runtime reliability changes do not require a strategy backtest when they cannot alter decisions. They still require static validation, targeted tests, startup smoke, and runtime verification where applicable.

Source:

- `VALIDATION_POLICY.md`
- `REFACTOR_AUDIT_POLICY.md`

## Permanent Per-Update Code Review

Workflow:

- `.github/workflows/refactor-audit.yml`

Every qualifying update now runs:

- repository-wide compile and AST validation;
- structural/mutation audit;
- architecture ownership contract validation;
- typed configuration parity validation;
- immutable Stage B model tests;
- StateStore Stage C shadow/parity tests;
- Stage D decision-comparison tests;
- Stage D runtime-capture tests;
- installation of declared runtime dependencies;
- the exact Gunicorn startup command against localhost;
- a post-deploy read-only Railway runtime snapshot.

The update fails when it introduces new critical structural debt, an unauthorized owner on a registered target, a new route/environment conflict, configuration drift, StateStore parity failure, immutable-model failure, runtime-shadow failure, or startup failure.

Existing debt remains visible and is removed in controlled batches rather than hidden or mass-deleted.

## Scheduled Audits

The consolidated workflow runs:

- weekly deep architecture audit: Sunday `12:30 UTC`;
- weekday after-close runtime/research snapshot: `23:15 UTC`;
- post-push runtime snapshot after a deployment-settle delay.

Artifacts retain phone-readable Markdown and machine-readable JSON for 30 days.

## Current Architecture Baseline

Latest calibrated audit from GitHub Actions run `30877811708`, head `58da8e70559a6dd33fa596d13ecdc157c57d4287`:

- Python files: 159
- Python source lines: 70,671
- internal import edges: 183
- static import cycles: 0
- module-level calls: 2,489
- import-time thread creations: 2
- persistent watchdog loops: 7
- genuinely high-frequency/busy watchdogs: 1
- dynamic mutation targets: 72
- overlapping mutation targets: 29
- environment keys observed: 869
- conflicting environment defaults: 3
- parameter names observed: 523
- parameter-owner conflicts: 10
- route literals: 187
- route overlaps: 5
- duplicate function-body groups: 65
- broad exception/pass handlers: 482
- provider-like calls inside loops: 1
- critical legacy findings: 29
- warning findings: 90
- new critical findings in that update: 0
- new warnings in that update: 0

The baseline is recorded in `ARCHITECTURE_AUDIT_BASELINE.md`.

## Stage A — Architecture Ownership Contract — Complete

Sources:

- `architecture_ownership_registry.json`
- `architecture_contract_validation.py`

Registered high-risk targets include:

- scanner ownership;
- entry/rotation ownership;
- state persistence;
- entry-quality evaluation;
- paper execution;
- exit management;
- market-data access;
- cycle orchestration;
- route overlaps;
- known environment conflicts.

Validated:

- registered callable targets: 10
- registered route conflicts: 5
- registered environment conflicts: 3
- ownership violations: 0
- legacy-owner removal allowed and recorded as progress
- new registered owners blocked
- new route overlaps and environment-default conflicts blocked

## Stage B — Typed Configuration and Immutable Models — Complete as Shadow Foundation

Sources:

- `typed_configuration_contract.json`
- `typed_configuration_snapshot.py`
- `typed_configuration_models.py`
- `shadow_decision_models.py`
- `test_architecture_stage_b.py`

Validated:

- canonical risk defaults frozen without changing effective values;
- explicit units documented for fractions, percentage points, scores, paths, minutes, and seconds;
- known conflicts preserved for controlled migration;
- immutable market, risk, position, signal, policy, candidate, and cycle models tested;
- runtime authority unchanged.

The typed configuration layer is not yet authoritative.

## Stage C — StateStore Shadow/Parity — Complete as Shadow Foundation

Sources:

- `state_store_contract.json`
- `state_store_shadow.py`
- `test_state_store_stage_c.py`

Validated:

- state-path precedence;
- existing environment/default conventions;
- required lock, retry, atomic-write, backup, and provenance capabilities;
- no state-file read or write by the shadow validator;
- no replacement of `save_state`;
- no runtime authority change.

The future `StateStore` interface is not yet authoritative.

## Stage D — Shadow Decision Comparison and Runtime Capture — Foundation Complete

Sources include:

- `shadow_decision_comparison_contract.json`
- `shadow_decision_comparison.py`
- `runtime_shadow_capture_contract.json`
- `runtime_shadow_capture.py`
- Stage D comparison and runtime-capture tests

Runtime adapter version:

- `runtime-shadow-capture-2026-08-03-v1-parity-baseline`
- mode `capture_parity_baseline`

The adapter:

- receives already-computed cycle inputs and outputs;
- creates immutable snapshots;
- records current-versus-shadow parity evidence;
- imports no trading runtime;
- calls no providers;
- replaces no callable;
- writes no files or paper state;
- places no orders.

The next evidence target remains at least 30 forward candidates and 20 one-day outcomes before any candidate policy can be promoted.

## Startup and Research Isolation

### Heavy research isolation

Historical V1/V2 research is disabled inside the single production web worker unless explicitly opted in with:

`WEB_WORKER_ALLOW_HEAVY_RESEARCH=true`

Forward-shadow capture and read-only status are preserved. Heavy historical research should eventually run in a separate worker/service.

### Guarded Python startup

Sources:

- `bootstrap/sitecustomize.py`
- `gunicorn.conf.py`
- `runtime_worker_registration.py`
- `bootstrap_wsgi.py`
- `Procfile`

Changes:

- research isolation is applied before application imports;
- the legacy eager pre-app `_register_all()` call is suppressed;
- the legacy 0.1-second, 1,800-iteration startup watchdog is suppressed;
- Flask constructor registration remains available;
- runtime registration has one explicit idempotent owner;
- a deferred WSGI dispatcher exposes `/bootstrap-status` while the legacy app loads;
- all normal routes delegate to the unchanged Flask app after registration.

### Exact startup smoke — Pass

GitHub Actions run `30877811708` used the declared runtime dependencies and exact production command.

Result:

- Gunicorn bound successfully;
- `/bootstrap-status` responded;
- deferred loader reached `ready`;
- `delegate_ready: true`;
- runtime registration `overall: pass`;
- research isolation active;
- full root route responded;
- startup reached ready in approximately 14 seconds in the latest smoke artifact.

This proves the repository start command and application code are functional in a clean Linux environment.

## Railway Config as Code

Source:

- `railway.json`
- commit `b81a7dfe60b0069446b54e48524441f4708b1659`

Pinned start command:

`DEFERRED_WSGI_BOOTSTRAP=true PYTHONPATH=bootstrap:. gunicorn bootstrap_wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`

Pinned health check:

- path: `/bootstrap-status`
- timeout: 120 seconds
- restart policy: on failure, maximum five retries

Both connected Railway deployment status contexts report success on current commits.

## Unresolved Railway Public Listener Boundary

Despite successful repository validation, exact-command startup smoke, and successful Railway deployment statuses, the public URL remains unreachable.

Latest bootstrap-aware post-deploy snapshot from run `30877811708` tested eight endpoints:

- `/bootstrap-status`
- `/`
- `/paper/status`
- `/paper/self-check`
- `/paper/performance-audit-status`
- `/paper/performance-audit-v2-status`
- `/paper/performance-ablation-v2`
- `/paper/performance-regime-report-v2`

Result:

- reachable endpoints: 0 of 8
- every request timed out
- listener reachable: false
- no bootstrap phase or application traceback was obtainable because the public listener itself did not answer

Conclusion:

The remaining failure is outside the tested repository startup path. The most likely boundaries are:

1. the public domain is attached to a different/stale Railway service;
2. the service has an explicit root directory or config-file path that prevents `/railway.json` from applying;
3. the service is using a dashboard start-command override or another deployment source;
4. the public domain belongs to one of the two connected Railway projects while validation is being observed on the other.

Do not make another trading, threshold, sizing, risk, wrapper, or startup-code change until the Railway service/domain configuration is verified.

## Required Manual Railway Verification

On the Railway service that owns `trading-bot-clean.up.railway.app`, verify:

1. **Networking**
   - the domain is attached to the currently deployed service;
   - it is not attached to an older duplicate project/service.

2. **Deploy / Config as Code**
   - repository root is `/`;
   - config file path is blank/default or explicitly `/railway.json`;
   - the effective start command matches the pinned deferred command above.

3. **Latest deployment**
   - deployed commit is current `main`;
   - deployment logs show Gunicorn binding to `0.0.0.0:$PORT`;
   - `/bootstrap-status` health check is recognized.

4. **Duplicate Railway projects**
   - identify which of these connected deployment contexts owns the public domain:
     - `splendid-creativity - web`
     - `dazzling-dedication - Trading-bot`
   - detach or archive the stale duplicate only after the domain owner is confirmed.

After that verification, rerun:

`https://trading-bot-clean.up.railway.app/bootstrap-status`

Then:

`https://trading-bot-clean.up.railway.app/paper/self-check`

## Current Freeze

Until the public Railway listener is restored:

- no new wrappers;
- no new watchdogs;
- no score, sizing, exposure, or risk changes;
- no forced positions;
- no automatic V2 policy promotion;
- no live or ML authority change;
- no removal of legacy owners without parity evidence.

## Next Engineering Sequence After Railway Recovery

1. Validate `/bootstrap-status` and `/paper/self-check` on the public service.
2. Confirm Stage D runtime-shadow telemetry appears in the one-link self-check.
3. Begin collecting forward candidate/outcome evidence.
4. Introduce the first authoritative typed configuration adapter only after parity snapshots show no behavior drift.
5. Migrate scanner ownership from 14 owners toward one explicit `SignalEngine` in small shadow-tested batches.
6. Migrate entry ownership from 13 owners toward one explicit `DecisionEngine` in small shadow-tested batches.
7. Migrate state persistence toward one `StateStore` only after state parity tests pass on production snapshots.
8. Remove route overlaps, duplicate parameter ownership, and unnecessary watchdogs incrementally.

## Current Definition of Done

Completed:

- continuous per-update structural review;
- weekly architecture audit;
- weekday/post-push runtime snapshot;
- repository-wide compile and safety gate;
- ownership contract;
- typed configuration parity foundation;
- immutable Stage B models;
- StateStore Stage C shadow foundation;
- Stage D decision comparison and runtime capture foundation;
- exact Gunicorn startup smoke gate;
- guarded startup and deferred WSGI dispatcher;
- Railway config-as-code start command and health check;
- all source, ownership, parity, shadow, and local startup gates passing.

Pending external action:

- verify Railway service/domain/config ownership and restore the public listener.

Pending after Railway recovery:

- production self-check validation;
- forward-shadow evidence collection;
- staged authoritative migration and legacy-owner reduction.
