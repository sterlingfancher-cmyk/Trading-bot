# Master System Audit and Architecture Consolidation Plan — 2026-08-20

## Purpose

This document is the controlling architecture plan for the paper-trading runtime. The goal is to stop treating runtime failures as an endless sequence of independent patches and instead remove the structural conditions that allow ownership, startup ordering, state, valuation, accounting, risk, execution, and persistence to disagree.

This is reliability architecture work. It does not authorize changes to strategy intent, signal thresholds, hard risk limits, live-trading authority, ML execution authority, or historical execution evidence.

## Audit evidence

The current full-repository structural audit from GitHub Actions run `32397510762` parsed the complete Python source surface on the PR #87 head that was subsequently merged to `main`.

Current inventory:

- Python files: 250
- Python source lines: 90,409
- internal import edges: 332
- import cycles: 0
- module-level calls: 2,742
- import-time activation calls: 54
- import-time thread creations: 2
- watchdog loops: 8
- busy/high-frequency watchdog loops: 1
- dynamic mutation targets: 92
- mutation overlaps: 34
- environment keys observed: 938
- environment-default conflicts: 5
- parameter names observed: 565
- parameter-owner conflicts: 10
- route literals: 197
- route overlaps: 5
- exact duplicate function-body groups: 80
- broad `except Exception: pass` sites: 540
- critical findings: 32
- warnings: 104
- informational findings: 137

Largest modules include `app.py` at 5,037 lines, `ml_recommendation_counterfactual_ledger.py` at 1,551 lines, `market_surge_deployment_mode.py` at 1,434 lines, `performance_audit_lab.py` at 1,384 lines, and `performance_audit_lab_v2.py` at 1,297 lines.

The audit reports zero import cycles and all current ownership/configuration/startup validation gates pass. The problem is not one circular import. The dominant problem is overlapping runtime authority and import-time composition.

## Root architectural failure classes

### 1. Startup order is behavior

There are 54 module-level activation calls plus Python startup customization, WSGI composition, data-integrity registration, runtime worker registration, and multiple watchdogs. A protection can therefore exist in the repository and still be installed after another module has already mutated state or called the unprotected boundary.

The 2026-08-19/20 fresh-risk-day defect is the concrete proof. The guard logic itself was valid, but it originally entered the composition after the larger WSGI import path had already had an opportunity to call the legacy risk boundary.

Target: one explicit startup composition owner. Importing a module must not silently activate trading/runtime behavior.

### 2. Public callables are repeatedly replaced

Production owners currently include:

- `scan_signals`: 14 runtime owners
- `try_entries_and_rotations`: 13 runtime owners
- `entry_quality_check`: 10 runtime owners
- `enter_position`: 9 runtime owners
- `run_cycle`: 5 runtime owners
- `manage_exits`: 3 runtime owners
- `download_prices`: 3 runtime owners

The effective behavior depends on wrapper order and which `apply/install/start_watchdog` path runs first. This is the largest source of recursion, stale-owner, and composition defects.

Target: one owner per public authority boundary. Strategy features become ordered policy layers or pure functions, not replacements of public callables.

### 3. State persistence has split ownership

`save_state` has 17 production mutation owners. `STATE_FILE` is independently interpreted across many modules and currently has conflicting fallback semantics (`state.json`, `None`, and empty-string forms). `STATE_FILENAME` is also duplicated.

`app.py` loads `portfolio = load_state()` during import. `state_io_hardening` installs later and wraps future reads/writes, which means the initial in-memory portfolio can be created before the later StateStore hardening boundary exists.

Target: one `StateStore` determines path, loading, locking, backups, atomic writes, schema version, and snapshot provenance before portfolio construction. Other modules do not own state-file I/O.

### 4. Portfolio, valuation, accounting, risk, and persistence are not one state machine

The current runtime can contain multiple representations of the same economic state: persisted portfolio fields, reconstructed accounting, canonical execution rows, journal mirrors, risk controls, cached marks, and audit projections. The August incidents proved those representations can disagree materially.

Target: a canonical state transition must have this order:

1. validated market data / execution input;
2. append or verify canonical execution evidence when an execution occurred;
3. deterministic portfolio projection;
4. deterministic valuation from protected marks;
5. risk-state update from that exact valuation snapshot;
6. atomic persisted canonical snapshot;
7. derived telemetry/reporting after commit.

Reporting, ML shadow, scanner telemetry, and dashboards must consume snapshots and must not be persistence owners.

### 5. Configuration meaning is duplicated

Current environment conflicts include:

- `STATE_FILE`
- `STATE_FILENAME`
- `AUTO_RUN_ENABLED`
- `MIN_ENTRY_SCORE_NEUTRAL`
- `EOD_ALLOCATION_WINDOW_MINUTES`

The audit also records a unit ambiguity for `MAX_INTRADAY_DRAWDOWN_PCT`: the account hard-risk owner uses fractional units while another surge-local setting uses percentage-point style values. `MAX_DAILY_DRAWDOWN_PCT` has similar mixed ownership.

Target: one immutable typed configuration object with namespaced fields and explicit units. Runtime modules receive config; they do not reinterpret environment variables independently.

### 6. Route and diagnostic composition is duplicated

Five exact route overlaps remain. Several modules replace Flask `view_functions` dynamically. This makes operator evidence depend on registration order and complicates proving which diagnostic is authoritative.

Target: one route registry with one owner per path. Diagnostics may aggregate from services but must not replace other handlers at runtime.

### 7. Exception suppression hides ownership failures

The full source contains 540 broad exception-pass sites. High concentrations exist in startup/composition modules such as `sitecustomize.py`, `wsgi.py`, `app.py`, entry/scanner layers, and state/persistence helpers.

Target: no silent broad exception suppression on startup, state, valuation, accounting, execution, risk, or persistence boundaries. Non-critical telemetry may degrade explicitly with a status payload, but authoritative failures must be visible and fail closed.

### 8. Background repair loops can recompose authority after startup

Eight persistent watchdog loops remain, including one five-second composition-repair loop in `performance_audit_composition_guard.py`. Repeated repair can make the runtime's callable graph change after startup.

Target: composition is immutable after successful startup. Health checks diagnose drift; they do not continuously rebuild trading authority.

### 9. Operational metadata has drifted

`PROJECT_HANDOFF_CURRENT.md` still identifies an older Railway domain as canonical, and the refactor workflow's runtime snapshot also probes that older domain, while the current operator-verified tests are being run against the `trading-bot-clean` service. This creates evidence-source ambiguity.

Target: one canonical deployment identifier/base URL in configuration and operator documentation, referenced by all read-only validation workflows.

## Target architecture

The target is a bounded package with explicit dependency direction:

- `trading.config` — immutable typed configuration and unit ownership
- `trading.state` — canonical snapshot models and authoritative `StateStore`
- `trading.market_data` — provider adapter, cache, provenance, freshness and plausibility
- `trading.valuation` — deterministic portfolio valuation from protected marks
- `trading.ledger` — adapter over the existing append-only canonical execution ledger
- `trading.accounting` — deterministic portfolio projection from baseline + canonical executions
- `trading.risk` — one risk lifecycle owner, including fresh-day initialization and halt state
- `trading.execution` — one paper execution service; preflight, ledger, projection and persistence transaction boundary
- `trading.signals` — one signal engine with ordered pure signal layers
- `trading.decision` — one decision engine with typed policy effects rather than wrapper replacement
- `trading.runtime` — one cycle orchestrator and one auto-runner lifecycle
- `trading.routes` — one route registry and read-only diagnostic adapters
- `trading.bootstrap` — the only application composition owner

Legacy modules remain adapters during migration and are deleted only after parity evidence proves their behavior has been absorbed or intentionally retired.

## Migration program

### Phase 0 — Freeze architectural debt growth

Before cutover work:

- no new public-callable replacement owners;
- no new import-time activation;
- no new import-time thread;
- no new state-file owner;
- no new route overlap;
- no new broad exception suppression on authoritative boundaries;
- no new watchdog that can mutate composition.

CI must block these categories from increasing.

### Phase 1 — Explicit bootstrap/composition

Create a single ordered composition graph. Remove automatic activation from ordinary module imports. Replace `sitecustomize`/`usercustomize` runtime registration, module-level `apply/install`, and repair loops with explicit bootstrap registration.

Acceptance:

- startup order is machine-readable and tested;
- pre-state/pre-risk protections install before state/risk consumers;
- no trading cycle starts before composition completes;
- import-time activation count trends to the minimal bootstrap-only set.

### Phase 2 — Canonical typed configuration

Move behavior-sensitive environment parsing to `trading.config`; normalize percent/fraction units and state path ownership. Legacy modules receive immutable configuration or compatibility properties.

Acceptance:

- environment conflicts: 5 -> 0;
- hard-risk units are explicit and tested;
- state path is resolved once;
- behavior-equivalence tests prove effective values are unchanged unless separately approved.

### Phase 3 — Authoritative StateStore and canonical portfolio snapshot

Promote the current shadow `trading.state` foundation into a real transactional store after parity. Initial state load must happen through the StateStore before portfolio construction.

Acceptance:

- production `save_state` owners: 17 -> 1;
- restart/reload produces identical canonical snapshot;
- no reporting/ML/telemetry module writes the authoritative state file;
- atomic write, fsync, lock and backup guarantees preserved.

### Phase 4 — Deterministic valuation + single risk engine

Valuation and risk operate on one immutable snapshot. Invalid/stale/catastrophic marks cannot seed equity or a fresh risk day. `day_start_equity`, `day_peak_equity`, daily loss and intraday drawdown have one owner.

Acceptance:

- risk baseline cannot initialize from invalid/non-positive valuation;
- valuation/accounting/risk evidence is internally identical at one snapshot version;
- no risk wrapper order dependency;
- prospective fresh-day test and restart test pass.

### Phase 5 — Canonical execution/accounting transaction

Use the existing append-only canonical execution ledger as execution evidence. One paper execution service owns entry, partial exit and full exit transitions. Duplicate/unmatched exits fail before mutation.

Acceptance:

- all new executions are canonical before portfolio projection;
- one transaction produces ledger evidence, accounting projection, valuation, risk update and persisted snapshot;
- no duplicate full exit, unmatched exit, or stale resurrected position can mutate canonical state;
- immutable historical rows remain untouched.

### Phase 6 — Signal and decision engine consolidation

Convert scanner/entry wrappers into ordered pure layers and typed policy effects.

Acceptance:

- `scan_signals`: 14 owners -> 1;
- `try_entries_and_rotations`: 13 owners -> 1;
- `entry_quality_check`: 10 owners -> 1;
- `enter_position`: 9 owners -> 1 execution service;
- no recursion-prone public callable replacement;
- baseline/candidate parity and strategy validation required before any behavior change.

### Phase 7 — Runtime, watchdog and route consolidation

One `CycleOrchestrator`, one runner lifecycle, one route registry. Health checks observe immutable composition instead of repairing it repeatedly.

Acceptance:

- `run_cycle`: 5 owners -> 1;
- route overlaps: 5 -> 0;
- busy/high-frequency composition watchdogs -> 0;
- no dynamic route handler replacement after startup.

### Phase 8 — Legacy retirement

Remove superseded wrappers, duplicated helpers, obsolete handoffs, parallel version families, dead compatibility shims, and redundant diagnostics only after static reference review, startup tests, parity evidence and runtime proof.

No module is deleted solely because a static analyzer calls it unused.

## Acceptance scoreboard

The architectural program is not complete until all of the following are true:

- mutation overlaps: 34 -> 0 for authoritative production targets
- `save_state` production owners: 17 -> 1
- `scan_signals` owners: 14 -> 1
- `try_entries_and_rotations` owners: 13 -> 1
- `entry_quality_check` owners: 10 -> 1
- `enter_position` owners: 9 -> 1
- environment conflicts: 5 -> 0
- route overlaps: 5 -> 0
- import-time runtime activation reduced to explicit bootstrap only
- import-time trading/repair threads: 0 outside bootstrap-owned runner creation
- no composition-repair watchdog
- no silent broad exception suppression on authoritative state/valuation/accounting/risk/execution/startup paths
- restart/reload canonical-state parity PASS
- exact Gunicorn startup smoke PASS
- repository/ownership/configuration audits PASS
- normal prospective fresh-day reset PASS
- normal forward paper session PASS
- clean active accounting audit PASS
- no change to hard risk limits, strategy intent, live authority, or ML execution authority unless separately approved and validated

## Relationship to Issue #82 and Issue #84

Issue #82 remains the current operational stabilization acceptance gate. No broad authoritative cutover should be used to manufacture a pass for the already-contaminated day. Prospective evidence remains required.

Issue #84 is the umbrella architecture migration. This master audit expands that work from the state/risk subsystem into the complete runtime authority graph while preserving the same shadow/parity-first cutover rule.

The immediate order is:

1. finish the prospective startup-order correction for the fresh-day guard;
2. verify the next genuine fresh-day transition rather than rewriting the current day;
3. keep the full architecture migration shadow/non-authoritative until stabilization evidence is clean;
4. then cut over one ownership boundary at a time with rollback and parity evidence;
5. remove legacy owners only after the replacement boundary is proven.
