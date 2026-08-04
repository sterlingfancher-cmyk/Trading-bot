# Automated Trading Project Handoff — Canonical Status, August 3, 2026 Evening

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: advisory only
- Hard-risk ladder unchanged:
  - 1.00% soft realized-loss pause
  - 2.50% hard realized-loss halt
  - 2.50% hard intraday-drawdown halt
  - 3.00% absolute daily-loss ceiling

## Latest User-Supplied Account Baseline

Historical snapshot from `2026-08-03 12:12:53 CDT`:

- equity: `$10,738.02`
- cash: `$10,240.9964`
- open paper position: `DELL`
- unrealized P&L: `+$3.22`
- realized lifetime: `+$734.82`
- wins/losses: 35/17
- scanner signals: 41
- no halt, self-defense condition, or active recursion

This is a historical baseline, not a claim about the current after-hours account state.

## Validated Trading Runtime Foundation

Previously validated:

- scanner order: opening surge → breakout → market participation → core
- exactly one bear-recovery wrapper
- exactly one Entry Pipeline X-Ray
- direct-core entry composition
- recursion-safe scanner and entry path
- neutral-only staged starter behavior
- bounded late-neutral participation
- one-link `/paper/self-check`

No trading thresholds, sizing, exits, hard-risk limits, live authority, or ML authority were changed during the architecture-audit work described below.

## Validation Policy

`VALIDATION_POLICY.md` is authoritative for engineering completion.

Trading-behavior changes require:

1. repository/static validation;
2. targeted unit and invariant tests;
3. baseline-versus-candidate backtest;
4. walk-forward or untouched holdout;
5. transaction-cost and slippage sensitivity;
6. regime and calendar segmentation;
7. ablation when multiple controls change;
8. forward shadow or bounded paper canary;
9. post-deploy `/paper/self-check`.

Documentation and genuinely read-only telemetry do not require a backtest when they cannot alter decisions.

## Permanent Refactor Audit

Canonical workflow:

- `.github/workflows/refactor-audit.yml`

### Every Python push or pull request

The workflow runs:

1. full structural audit;
2. new-critical-debt comparison against the base commit;
3. architecture ownership-contract validation;
4. typed configuration parity validation;
5. immutable Stage B model tests;
6. StateStore shadow parity validation;
7. Stage C tests;
8. JSON/Markdown artifact publication;
9. visible `refactor-audit` commit status.

The gate blocks:

- new critical callable mutation debt;
- unauthorized owners on protected targets;
- new route overlaps;
- new environment-default conflicts;
- canonical configuration drift;
- loss of current StateStore safety capabilities;
- shadow models gaining runtime or order authority.

### Weekly

A full deep architecture audit runs Sunday at `12:30 UTC` and retains reports for 30 days.

### Weekdays after close

A bounded, concurrent, read-only Railway snapshot runs at `23:15 UTC`, or manually through workflow dispatch.

It checks:

- core web connectivity;
- `/paper/self-check`;
- paper status;
- V1/V2 research status;
- persisted V2 ablation and regime reports.

It does not start a trading cycle, launch research, mutate state, or place orders.

Runtime snapshots intentionally do not run after every commit; repeated post-commit probing could create unnecessary load during multi-commit refactors.

## Architecture Audit Baseline

Canonical document:

- `ARCHITECTURE_AUDIT_BASELINE.md`

Latest validated Stage C audit:

- GitHub Actions run: `30875703784`
- head commit: `eaf02e521b78bf9204426bb8f74331d9f353e9c8`
- structural audit: pass
- ownership contract: pass
- typed configuration: pass
- Stage B tests: pass
- StateStore shadow parity: pass
- Stage C tests: pass
- new critical findings: 0
- new warnings: 0

Current architecture surface:

- Python files: 152
- source lines: 69,210
- import cycles: 0
- mutation targets: 72
- overlapping mutation targets: 29
- environment-default conflicts: 3
- parameter-owner conflicts: 10
- route overlaps: 5
- critical findings: 29
- warnings: 90
- broad exception/pass paths: 482

Highest ownership debt:

- `scan_signals`: 14 legacy owners
- `try_entries_and_rotations`: 13 legacy owners
- `save_state`: 16 legacy owners
- `entry_quality_check`: 10 legacy owners
- `enter_position`: 9 legacy owners

## Stage A — Ownership Contracts — Complete

Sources:

- `architecture_ownership_registry.json`
- `architecture_contract_validation.py`

Validated:

- protected callable targets: 10
- protected route targets: 5
- protected environment targets: 3
- ownership violations: 0
- removal of legacy owners is allowed and recorded as progress
- undeclared new owners are blocked

Future owner names are descriptive only and have no runtime authority.

## Stage B — Typed Configuration and Shadow Models — Complete

Canonical sources:

- `typed_configuration_contract.json`
- `typed_configuration_snapshot.py`
- `shadow_decision_models.py`
- `test_architecture_stage_b.py`

Validated:

- typed configuration status: pass
- violations: 0
- known conflicts/ambiguities preserved: 5
- canonical defaults present
- immutable signal, market, risk, position, policy, candidate, and cycle models pass tests
- shadow authority only
- no runtime imports or order methods

Known preserved conflicts include:

- neutral entry-score fallback: `0.0140` versus advisory `0.033`
- `STATE_FILE` diagnostic fallbacks
- EOD timing dynamic ownership
- drawdown fraction versus percentage-point naming

A duplicate typed-configuration implementation was removed before promotion, preserving one canonical validation path.

## Stage C — StateStore Shadow Parity — Foundation Complete

Sources:

- `state_store_contract.json`
- `state_store_shadow.py`
- `test_state_store_stage_c.py`

Validated current capabilities:

- atomic replace
- file and directory fsync
- thread locking
- file locking when supported
- shared read and exclusive write paths
- retrying reads
- latest, largest, and prewrite backups
- backup fallback reads
- non-overlapping cycle guard
- canonical `STATE_FILE=state.json`

StateStore shadow result:

- status: pass
- missing symbols: 0
- missing calls: 0
- default drift: 0
- capability drift: 0
- typed configuration drift: 0
- observed `save_state` owners: 16

This is not a state-authority migration. The shadow validator does not read/write the production state file, replace `save_state`, or change state paths.

## Heavy Research Isolation

The single Gunicorn web worker previously contained several paths capable of automatically starting or resuming multi-year V1/V2 research jobs. That could starve web/status requests.

Current web-worker boundary:

- V1 automatic historical backtest disabled
- V2 automatic historical backtest disabled
- V2 heavy research disabled in the web worker by default
- stale Railway environment values cannot silently re-enable it
- async/recovery historical research workers are not imported into the web worker
- forward-shadow and read-only status capability remain
- manual/dedicated research must be separated from production execution

Key isolation commit:

- `0866ff5a0a94f37a14d629a7a8e9a95f4507bc4c`

This changes research process placement only; it does not change trading behavior.

## Current Runtime Connectivity Note

Earlier GitHub Actions and an independent external fetch timed out against the Railway endpoints after market close. Railway deployment statuses were successful, but endpoint responsiveness had not yet been confirmed through a completed scheduled/manual snapshot at the time of this handoff update.

Do not interpret that connectivity issue as a failed structural audit. Static architecture, ownership, configuration, shadow-model, and StateStore gates all passed independently.

## Current Freeze

Until forward shadow comparison exists:

- do not add entry wrappers, watchdogs, starter valves, or threshold exceptions;
- do not widen hard-risk limits;
- do not force additional positions;
- do not use raw Kelly sizing;
- do not promote research parameters automatically;
- do not remove current state or callable owners in bulk;
- allow urgent operational repairs and controlled refactor stages only.

## Next Engineering Stage — Decision Comparison Recorder

Build a read-only Stage D comparison path:

1. capture the same immutable cycle input used by the current engine;
2. translate scanner candidates, market, risk, and positions into shadow models;
3. record the existing engine’s decision and reasons;
4. run a new read-only evaluator against the same snapshot;
5. compare selected/rejected symbols, terminal reasons, score changes, size multipliers, risk, exposure, and eligibility;
6. persist comparison telemetry only;
7. place no orders and change no runtime authority;
8. collect at least 30 forward candidates and 20 one-day outcomes before considering authority migration.

## Recent Milestone Commits

- `6e8a29ae7186538cbe9f243a839b1fd7c1811b97` — ownership stage recorded
- `43ac279b3afb72fc41ab1463898bdedf34d79084` — typed configuration parity enforced
- `4dc2194270ee2816a4eb2332fb3dafd68c136e9e` — immutable shadow decision models
- `b274a5a0e637179d7aa20d384368d9d4f0e59e49` — canonical Stage B tests enforced
- `0866ff5a0a94f37a14d629a7a8e9a95f4507bc4c` — heavy research isolated
- `499c284134eb2c0b3326d08a78346b2b2966c45c` — StateStore shadow validator
- `eaf02e521b78bf9204426bb8f74331d9f353e9c8` — Stage C gate enforced
- `302843b0e7b4d07a24e9e9bb2438bd3c24239126` — runtime snapshots limited to schedule/manual
- `41953a8fe5cc19a29066f29f55b8be73962ec9b9` — architecture baseline updated
