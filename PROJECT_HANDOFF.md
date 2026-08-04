# Automated Trading Project Handoff — Canonical Status, August 4, 2026

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Canonical live paper service: `https://web-production-e1796.up.railway.app`
- Railway owner: `splendid-creativity` → `web`
- Previous URL `https://trading-bot-clean.up.railway.app` is not attached to the validated Splendid service and must not be used as the routine test URL until its domain is deliberately migrated.
- Mode: paper only
- Live broker authority: none
- ML execution authority: advisory only
- Heavy historical research authority in the web worker: disabled

Hard-risk ladder remains unchanged:

- 1.00% soft realized-loss pause
- 2.50% hard realized-loss halt
- 2.50% hard intraday-drawdown halt
- 3.00% absolute daily-loss ceiling

No change in this recovery/refactor milestone altered signal formulas, entry floors, paper sizing rules, hard-risk limits, existing execution authority, live authority, or ML authority.

## Latest Validated Runtime Evidence

GitHub Actions runtime snapshot:

- workflow run: `30915881450`
- rerun artifact: `8895345458`
- head: `7c33c268c143603a8438f884e85ebb7c0cf3d224`
- snapshot generated: `2026-08-04 09:00:53 CDT`
- listener reachable: yes
- application ready: yes
- operational endpoints reachable: 7 of 8
- `/paper/self-check`: pass
- only failed probe: the nonessential root/dashboard route `/`

Latest Splendid-service paper account snapshot:

- cash: `$9,878.62`
- equity: `$9,999.56`
- open paper position: `TSM`
- unrealized P&L: `-$0.44`
- realized P&L: `$0.00`
- execution rows: 1
- last successful automatic cycle: `2026-08-04 08:58:20 CDT`
- scanner signals in latest cycle: 13
- no active recursion, halt, self-defense condition, or auto-runner error

This `$10,000` Splendid-service paper account is a separate runtime state boundary from the historical `DELL` account snapshot previously observed on the older service. Do not combine their balances, trades, or performance statistics.

## Continuous Validation Policy

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

Documentation, audit tooling, read-only telemetry, startup reliability, and classification-only changes do not require a strategy backtest when they cannot alter trading decisions. They still require static validation, targeted tests, exact startup smoke, deployment validation, and runtime verification where applicable.

Canonical policies:

- `VALIDATION_POLICY.md`
- `REFACTOR_AUDIT_POLICY.md`

## Permanent Per-Update Review

Workflow:

- `.github/workflows/refactor-audit.yml`

Every qualifying update now checks:

- repository-wide compile and AST safety contracts;
- structural mutation and overlap audit;
- architecture ownership contracts;
- typed-configuration parity;
- immutable Stage B models;
- StateStore Stage C shadow parity;
- Stage D decision-comparison and runtime-capture tests;
- self-check runtime classification tests;
- one-shot core-mutation ownership;
- final cycle-observer ordering;
- declared runtime dependency installation;
- the exact production Gunicorn command against localhost;
- the live Splendid Railway runtime after deployment.

The update fails when it introduces a new critical mutation/ownership conflict, a new route or environment conflict, configuration drift, StateStore parity failure, immutable-model failure, shadow-capture failure, startup failure, or a known one-shot core mutation inside a repeated repair loop.

Scheduled controls:

- weekly deep architecture audit: Sunday `12:30 UTC`;
- weekday after-close runtime/research snapshot: `23:15 UTC`;
- post-push runtime snapshot after a deployment-settle delay.

Artifacts retain phone-readable Markdown and machine-readable JSON for 30 days.

## Current Architecture Baseline

Latest calibrated structural audit:

- workflow run: `30915881450`
- head: `7c33c268c143603a8438f884e85ebb7c0cf3d224`
- status: pass
- new critical findings: 0
- new warnings: 0
- Python files: 161
- Python source lines: 71,192
- internal import edges: 185
- static import cycles: 0
- module-level calls: 2,497
- import-time thread creations: 2
- persistent watchdog loops: 7
- genuinely busy/high-frequency watchdogs: 1
- dynamic mutation targets: 74
- overlapping mutation targets: 29
- environment keys: 869
- conflicting environment defaults: 3
- parameter names: 523
- parameter-owner conflicts: 10
- route literals: 187
- route overlaps: 5
- duplicate function-body groups: 65
- broad exception/pass handlers: 482
- provider-like calls inside loops: 1
- critical legacy findings: 29
- warning findings: 90

Ownership, typed configuration, StateStore parity, immutable models, runtime-shadow tests, classification tests, and exact startup smoke all passed.

The legacy counts remain refactor debt. They are not permission to mass-delete import-side-effect modules or weaken safety controls.

## Stage A — Architecture Ownership Contract — Complete

Sources:

- `architecture_ownership_registry.json`
- `architecture_contract_validation.py`

Validated:

- registered callable targets: 10
- registered route conflicts: 5
- registered environment conflicts: 3
- ownership violations: 0
- new registered owners blocked
- removal of legacy owners allowed and measured as progress

## Stage B — Typed Configuration and Immutable Models — Shadow Foundation Complete

Sources:

- `typed_configuration_contract.json`
- `typed_configuration_snapshot.py`
- `typed_configuration_models.py`
- `shadow_decision_models.py`
- `test_architecture_stage_b.py`

The layer documents and validates units and effective defaults but is not yet authoritative.

## Stage C — StateStore Shadow/Parity — Shadow Foundation Complete

Sources:

- `state_store_contract.json`
- `state_store_shadow.py`
- `test_state_store_stage_c.py`

Validated without replacing `save_state` or changing the active state path:

- path precedence;
- locking;
- retry behavior;
- atomic writes;
- backups;
- provenance;
- cycle-overlap protection.

## Stage D — Runtime Shadow Capture — Live Parity Baseline Validated

Sources:

- `shadow_decision_comparison_contract.json`
- `shadow_decision_comparison.py`
- `runtime_shadow_capture_contract.json`
- `runtime_shadow_capture.py`
- `run_report_guard.py`
- `test_runtime_shadow_capture.py`

Runtime adapter:

- version: `runtime-shadow-capture-2026-08-03-v1-parity-baseline`
- mode: `capture_parity_baseline`
- observer only
- no provider calls
- no file authority
- no broker/order authority
- no strategy, threshold, sizing, or risk changes

First validated live capture:

- cycle ID: `observed-2026-08-04 08:58:20 CDT`
- captured cycles: 1
- captured candidates: 28
- parity: true
- divergence: none
- selected symbols in that cycle: none
- independent shadow policy active: false
- forward promotion evidence eligible: false

The 28 parity-capture candidates prove the translation/comparison plumbing. They do **not** count toward the promotion minimum because no independent candidate policy is active.

Before any independent policy can gain paper authority, it must separately accumulate at least:

- 30 forward candidates after the policy is frozen;
- 20 one-day outcomes;
- required historical backtest/walk-forward evidence;
- transaction-cost and slippage sensitivity;
- regime review;
- bounded paper-canary approval.

## Railway Recovery and Configuration Ownership

Root cause of the public-listener outage:

- `railway.toml` still supplied the obsolete `gunicorn wsgi:app` start command;
- `railway.json` supplied the validated deferred-bootstrap command;
- Railway therefore had two competing config-as-code sources;
- the previously used `trading-bot-clean` URL was not attached to the Splendid `web` service.

Completed repair:

- obsolete `railway.toml` deleted in commit `b2a32911706eb143cea7f7e975032138302d8dcf`;
- one canonical `railway.json` retained;
- CI now fails if multiple Railway config files reappear;
- live runtime collector now targets `web-production-e1796.up.railway.app`;
- both connected Railway deployment contexts report successful deployments.

Canonical Railway command:

`DEFERRED_WSGI_BOOTSTRAP=true PYTHONPATH=bootstrap:. gunicorn bootstrap_wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`

Canonical health check:

- `/bootstrap-status`

Latest bootstrap evidence:

- status: ready
- phase: delegating
- `delegate_ready: true`
- runtime registration: pass
- research isolated: true

## Auto-Runner Ownership and Runtime Classification

The existing `app.ensure_auto_thread` loop now starts through the explicit runtime-registration owner after composition.

Runtime registration:

- version: `runtime-worker-registration-2026-08-04-v4-final-cycle-observer`
- starts the existing app-owned runner only;
- creates no new runner type;
- synchronizes stale diagnostic state from the authoritative process-global flag;
- installs the final cycle observer before starting the runner.

The self-check now distinguishes:

- persisted `thread_started` state;
- observed recent automatic attempts;
- actual active error state;
- intentionally deferred historical research.

An isolated `not_run` historical backtest is reported as `deferred_to_research_worker`, not as a web-runtime failure. A real research error remains a warning.

## Recursion Incident and Ownership Repair

The first market-open automatic cycle exposed a genuine callable cycle:

`controlled_redeployment_starter_sleeve` → `paper_underdeployment_repair` → `controlled_redeployment_starter_sleeve`

Root cause:

- `usercustomize._watchdog()` repeatedly reapplied `controlled_redeployment_starter_sleeve`;
- that module replaces the canonical core function pointer and stores the prior callable;
- after another layer wrapped the core, reapplication captured the downstream wrapper and formed an A → B → A loop.

Repair:

- `controlled_redeployment_starter_sleeve` is registered as a one-shot core mutation;
- it is absent from the repeated watchdog repair loop;
- CI parses `usercustomize.py` and fails if it is returned to the repeated loop or removed from the one-shot registry;
- no strategy rule, threshold, sizing rule, or risk limit was removed.

Validated outcome:

- automatic market-open cycle succeeded;
- recursion error active: false;
- recursion error historical: false;
- scanner stack ordered and cycle-free;
- entry composition stable and recursion-safe;
- bear/X-Ray ownership counts remain exactly one each.

## Current Runtime Self-Check

Latest result:

- overall: pass
- components checked/passed/warned: `9/9/0`
- deferred advisory components: `performance_evidence`
- base failures: none
- next action: none
- auto runner enabled and active
- last error: none
- risk halted: false
- self-defense active: false
- Stage D capture state: captured
- Stage D parity: true

Routine link:

`https://web-production-e1796.up.railway.app/paper/self-check`

Bootstrap link:

`https://web-production-e1796.up.railway.app/bootstrap-status`

## Current Freeze

Until an independent shadow policy is backtested and frozen:

- no new wrappers or watchdogs;
- no score, sizing, exposure, or hard-risk changes;
- no forced positions;
- no automatic V2 parameter promotion;
- no live or ML authority change;
- no legacy-owner removal without parity evidence;
- no raw Kelly sizing.

## Next Engineering Sequence

1. Allow the parity-capture adapter to collect additional normal market cycles and verify stable translation across entries, no-entry cycles, and exits.
2. Move heavy V1/V2 historical research to a dedicated Railway research worker/service or another isolated execution environment.
3. Complete and review baseline-versus-candidate V2 walk-forward, regime, ablation, cost, and slippage reports outside the production web worker.
4. Define one independent typed shadow-policy candidate from reviewed evidence; keep it comparison-only and freeze its parameters.
5. Collect at least 30 eligible forward candidates and 20 one-day outcomes from that independent policy.
6. Introduce the first authoritative typed-configuration adapter only after parity evidence shows no behavioral drift.
7. Consolidate scanner ownership toward one explicit `SignalEngine` in small shadow-tested batches.
8. Consolidate entry ownership toward one explicit `DecisionEngine` in small shadow-tested batches.
9. Migrate persistence toward one `StateStore` only after production snapshot parity.
10. Remove route overlaps, duplicate parameter owners, and unnecessary watchdogs incrementally.

## Current Definition of Done

Completed:

- public Splendid Railway service restored;
- one canonical Railway config-as-code source;
- permanent Railway-config conflict check;
- repository-wide compile and safety gate;
- continuous per-update structural review;
- weekly deep architecture audit;
- weekday/post-push runtime snapshot;
- exact Gunicorn startup smoke;
- heavy historical research isolation;
- architecture ownership contract;
- typed-configuration shadow foundation;
- immutable decision models;
- StateStore shadow foundation;
- auto-runner registration ownership;
- stale runtime diagnostic classification repair;
- core-mutation recursion repair;
- live Stage D parity capture.

Pending:

- more parity-capture cycles across diverse runtime outcomes;
- dedicated research execution environment;
- completed V2 evidence review;
- independent frozen shadow policy;
- forward candidate/outcome minimums;
- staged authoritative migration and legacy-owner reduction.
