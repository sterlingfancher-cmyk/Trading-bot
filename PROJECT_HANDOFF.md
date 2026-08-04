# Automated Trading Project Handoff — Canonical Status, August 3, 2026 Evening

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: advisory only
- Hard-risk ladder remains:
  - 1.00% soft realized-loss pause
  - 2.50% hard realized-loss halt
  - 2.50% hard intraday-drawdown halt
  - 3.00% absolute daily-loss ceiling

## Latest Supplied Account Baseline

The latest user-supplied all-in-one snapshot remains the `2026-08-03 12:12:53 CDT` observation:

- equity: `$10,738.02`
- cash: `$10,240.9964`
- open paper position: `DELL`
- unrealized P&L: `+$3.22`
- realized today: `$0.00`
- realized lifetime: `+$734.82`
- completed exits: 52
- wins/losses: 35/17
- scanner signals: 41
- no halt, self-defense condition, active recursion, or active auto-runner error

This is a historical baseline, not a claim about the current evening account state.

## Validated Runtime Foundation

Previously validated:

- canonical scanner order:
  1. opening surge
  2. one breakout layer
  3. one market-participation layer
  4. core scanner
- one bear-recovery wrapper
- one Entry Pipeline X-Ray
- direct-core entry composition
- no scanner or entry recursion
- all-in-one `/paper/self-check`
- neutral-only starter staging
- bounded late-neutral participation

Routine post-deploy endpoint remains:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Open individual diagnostics only when `summary.failing_components` identifies them.

## Transitional Runtime Architecture

Gunicorn currently imports and activates multiple reliability, ownership, participation, policy, and research modules during `post_worker_init`.

Important architectural consequence:

- the system still relies on import-time activation, watchdog threads, callable replacement, and runtime configuration mutation;
- the newly added central policy reduces conflicting parameter ownership but does not eliminate the underlying mutation architecture;
- no additional wrapper, watchdog, starter valve, or one-off threshold exception should be added while the architecture audit and canonical-engine migration are pending.

## Central Regime-Adaptive Paper Policy

Source:

- `paper_regime_adaptive_policy.py`
- version `paper-regime-adaptive-policy-2026-08-03-v1`
- source commit `263b947f29d1a90d0a8d7cee0e4a5f40598ccf1a`
- activation commit `08f73ddb6c36d1c827b115ba0b98a167cdff7d74`

Purpose:

- provide one central owner for a bounded whitelist of capacity, exposure, starter, allocation, cash-reserve, spacing, and participation-valve parameters;
- select a profile from:
  - `strong_risk_on`
  - `risk_on`
  - `constructive`
  - `neutral`
  - `defensive`
  - `risk_off`;
- restore more coherent capital deployment without adding another entry wrapper.

Safety boundary:

- paper only;
- does not lower the primary `app.py` entry-score floors;
- does not modify the 3% daily-loss ceiling or 2.5% hard drawdown/realized-loss limits;
- does not replace `scan_signals` or `try_entries_and_rotations`;
- does not place orders directly;
- does not grant live or ML authority.

This is a transitional configuration owner, not the final refactored architecture.

## Performance Research Lab V2

Source:

- `performance_audit_lab_v2.py`
- version `performance-audit-lab-v2-2026-08-03-v1`
- source commit `3932751504a2ac25ca4b9c90d7da787d4cc45933`

Methodology:

- next-session-open execution assumption;
- five-year default research period;
- up to 45 symbols by default;
- 8 basis points transaction-cost assumption;
- full-history rolling walk-forward;
- 252-session training windows;
- 63-session test windows;
- regime segmentation;
- calendar-year reporting;
- static and adaptive comparison profiles;
- one-variable-at-a-time ablation;
- explicit survivorship, universe-selection, daily-bar, provider-latency, and inverse-ETF proxy warnings.

Activation gate built into the report:

- automatic strategy promotion: false;
- forward-shadow confirmation required;
- minimum forward candidates: 30;
- minimum one-day outcomes: 20;
- paper only.

The research lab is advisory only and must not automatically change runtime policy.

## Resumable V2 Research Runner

Source:

- `performance_audit_v2_async_route.py`
- version `performance-audit-v2-resumable-route-2026-08-03-v2`
- initial asynchronous route commit `f7c9b946790ec16f249c3e17116d10349bf68321`
- activation commit `f18a94965513cd68e565e203de2222ab80ce1901`
- resumable/staged-ablation commit `0cc7e4563e99f81b130a3370029ed5546ba73da7`

Recovery source:

- `performance_audit_v2_recovery_guard.py`
- version `performance-audit-v2-recovery-guard-2026-08-03-v1`
- source commit `c6e5269821f9e159934f29f5b5a3314ccc2877d2`
- activation commit `6ec236af148a73af3992365a32681e007f978735`
- validation-workflow inclusion commit `0880135ee63f4aa663767325455d551f5253cdca`

Read-only endpoints:

- `/paper/performance-audit-v2-status`
- `/paper/performance-backtest-v2`
- `/paper/performance-backtest-v2-start`
- `/paper/performance-ablation-v2`
- `/paper/performance-regime-report-v2`
- `/paper/performance-v2-recovery-status`

The heavy run executes outside the HTTP request, checkpoints the core walk-forward result, stages ablation separately, and can resume an interrupted queued/running request after a Railway worker restart.

Source deployment is confirmed. The actual latest V2 report has not yet been reviewed in this conversation; therefore no performance conclusion or parameter promotion is authorized.

## Change Validation Policy

Source:

- `VALIDATION_POLICY.md`
- commit `a4928d0422fe47601423e9f56bcd5f74f7db6c52`

Rule:

A backtest and forward test are mandatory for changes that can alter strategy, scanner output, ranking, score, entry, exit, sizing, exposure, capacity, or risk.

They are not mandatory for documentation-only or purely telemetry-only changes that cannot affect decisions.

Validation classes:

1. documentation/CI only
2. telemetry/diagnostics
3. runtime reliability/composition
4. trading behavior
5. live/broker authority — not authorized

Trading-behavior completion requires:

- static and unit validation;
- baseline-versus-candidate backtest;
- walk-forward or untouched holdout;
- transaction-cost and slippage sensitivity;
- regime and calendar segmentation;
- ablation when multiple controls change;
- forward shadow or bounded paper canary;
- post-deploy `/paper/self-check`.

"Forward test" means unseen future paper observations after the candidate is frozen. It is not a prediction of future prices.

## Repository-Wide Validation Gate

Source:

- `repository_validation.py`
- initial commit `1f7ecfe97c6db1b98d50109be284362efce3bc84`
- advisory-call refinement commit `13a9d5066defe3a51be2b259fbd2d25b94671005`

Workflow:

- `.github/workflows/performance-audit-validation.yml`
- repository-wide workflow commit `753db51a157a76eb5c0b527d7fecce03fb8b4599`

The gate runs under Python 3.11 and:

- compiles and parses every tracked Python file;
- checks protected `app.py` defaults:
  - `MAX_DAILY_LOSS_PCT=0.03`
  - `MAX_INTRADAY_DRAWDOWN_PCT=0.025`
  - manual after-hours trading defaults off;
- verifies the central adaptive policy defaults to paper-only;
- rejects central-policy mutations of hard-risk constants and primary entry-score floors;
- rejects replacement of `scan_signals` or `try_entries_and_rotations` by the central policy;
- checks advisory research modules for broker/order-submission calls;
- inventories module-level side effects and dynamic mutations;
- classifies changed files and lists the required validation gates;
- uploads `repository_validation_report.json` as a GitHub Actions artifact.

Railway successfully deployed the validation commits. The files are non-runtime and do not alter trading behavior.

The GitHub Actions artifact/result still needs direct review before the repository-wide gate is treated as fully validated.

## Required Validation Going Forward

### Every Python change

- repository-wide compile and AST contracts;
- targeted unit/invariant tests;
- change classification;
- review of the generated validation report.

### Runtime reliability or composition change

- mocked or targeted integration test;
- worker startup smoke test;
- one successful paper cycle;
- `/paper/self-check`;
- backtest only when decision output can change.

### Trading-behavior change

- baseline and candidate backtests on identical assumptions;
- full walk-forward or untouched holdout;
- realistic costs and slippage;
- regime-segmented metrics;
- ablation;
- forward shadow or bounded paper canary;
- `/paper/self-check`.

### Documentation or telemetry-only change

- no mandatory backtest when the change cannot alter decisions;
- still require static validation and post-deploy smoke testing when runtime code is touched.

## Current Freeze

Until the architecture audit and shadow-decision path are complete:

- do not add new entry wrappers, watchdogs, starter valves, or one-off threshold exceptions;
- do not widen hard-risk limits;
- do not use raw Kelly sizing;
- do not force additional positions;
- do not promote V2 research parameters automatically;
- allow urgent operational repairs and testing/refactor foundation work only.

## Next Engineering Sequence

1. Review the repository-wide validation artifact and correct any failures.
2. Review the completed V2 backtest, walk-forward, regime, and ablation reports.
3. Produce the full dependency, import-side-effect, wrapper, watchdog, constraint, and parameter-ownership map.
4. Create canonical interfaces for data, signals, risk policy, sizing, decision, execution, state, and telemetry.
5. Build a shadow decision engine that records old-versus-new decisions without placing orders.
6. Collect at least 30 forward candidates and 20 one-day outcomes before promoting a candidate policy.
7. Migrate authority only after tests and forward evidence pass.
8. Remove legacy wrappers and duplicated controls in controlled batches.

## Definition of Done for the Current Milestone

Completed:

- central paper regime-adaptive configuration owner;
- advisory full-history V2 performance lab;
- resumable asynchronous research runner;
- persistent research recovery watchdog;
- formal validation policy;
- repository-wide static validation script;
- Python-change GitHub Actions gate;
- successful Railway deployment of the non-runtime testing foundation.

Pending:

- direct review of the GitHub Actions validation artifact;
- direct review of the latest V2 research report;
- architecture and constraint inventory;
- shadow forward-testing path;
- forward evidence before any further policy promotion.
