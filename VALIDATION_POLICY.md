# Change Validation Policy

This repository is a paper-trading system. Validation must be proportional to the type of change. A historical backtest is not a substitute for runtime testing, and a runtime smoke test is not a substitute for out-of-sample strategy evidence.

## Core Rule

No trading-behavior change is considered complete when the code merely compiles or Railway deploys successfully.

A trading-behavior change must pass:

1. static and unit validation;
2. baseline-versus-candidate historical testing;
3. walk-forward or untouched holdout testing;
4. transaction-cost and slippage sensitivity;
5. regime-segmented review;
6. a forward shadow or bounded paper canary;
7. the post-deploy `/paper/self-check`.

"Forward test" means observation on data and market cycles that were not available when the change was designed. It does not mean predicting future prices.

## Mandatory Exact-Head Change Safety Audit

Every future pull request that can affect Python code, runtime behavior, configuration, persistence, workflows, startup, diagnostics, strategy, accounting, valuation, risk, execution, or repository validation must pass the canonical `Change Safety Audit` on the exact pull-request head SHA before merge or deployment.

A local unit test or stage-specific check is never sufficient by itself. The mandatory audit must:

- classify the changed surface and affected authority boundaries;
- run targeted/impact-aware regression tests selected from the changed paths;
- always run the canonical state, valuation, accounting, risk, and canary invariant suite;
- run repository-wide safety validation and Railway configuration validation;
- run the structural refactor audit with no new critical findings;
- validate architecture ownership and typed configuration parity;
- block any architecture-debt increase;
- run the exact Gunicorn/bootstrap startup smoke;
- verify the checked-out commit SHA exactly matches the pull-request head SHA;
- emit a machine-readable `change_safety_audit_report.json` tied to that SHA.

The audit fails closed when any required component is missing, stale, skipped, incomplete, or failing. A passing audit on an older commit does not satisfy a newer pull-request head. Repository rules/branch protection must require the `Change Safety Audit` check before merge where repository permissions support enforcement.

The gate itself must retain regression proof that a seeded breaking condition is rejected and an all-green safe change is accepted. No alternate workflow or path-only change may bypass the canonical audit.

## Validation by Change Type

### Documentation, comments, formatting, and non-runtime workflow edits

Required:

- syntax or schema validation where applicable;
- review of the changed files.

Backtest required: no.

Forward test required: no.

### Telemetry-only and diagnostic changes

Examples:

- status payloads;
- logging;
- recovered-error labeling;
- handoff updates;
- read-only reports.

Required:

- compile and static validation;
- targeted unit or payload tests;
- startup or route smoke test when the runtime is touched;
- `/paper/self-check` after deployment.

Backtest required: only when the change can alter scanner, decision, sizing, entry, exit, or risk output.

Forward test required: normally no, unless runtime timing or state persistence changes.

### Runtime reliability, provider, state, composition, and ownership changes

Required:

- compile and static validation;
- mocks or integration tests for the affected boundary;
- worker startup test;
- recursion and ownership invariants;
- one successful paper cycle;
- `/paper/self-check`.

Backtest required: only when decision output can change.

Forward test required: at least one bounded paper cycle or market session when timing, state, provider behavior, or execution sequencing changes.

### Strategy, scanner, ranking, score, entry, exit, sizing, exposure, capacity, or risk changes

Required:

- compile and static validation;
- targeted unit and invariant tests;
- baseline-versus-candidate backtest using the same data and assumptions;
- full-history walk-forward or a genuinely untouched holdout period;
- realistic transaction costs and slippage;
- results by market regime and calendar segment;
- trade-count, turnover, drawdown, exposure, and concentration review;
- one-variable-at-a-time ablation when multiple controls change;
- forward shadow mode where available, otherwise a bounded paper canary;
- `/paper/self-check` after deployment.

Backtest required: yes.

Forward test required: yes.

### Live authority, broker credentials, or real-order changes

Not authorized. The system remains paper-only.

## Minimum Evidence

A candidate does not pass merely because total return increases. Review at minimum:

- total return;
- annualized return when the period supports it;
- maximum drawdown;
- Sharpe or another risk-adjusted metric;
- win rate and profit factor;
- trade count;
- turnover;
- average exposure;
- worst regime;
- worst calendar segment;
- sensitivity to costs and delayed execution;
- divergence between training, validation, and holdout results.

## Promotion Rules

- Do not optimize and evaluate on the same period.
- Do not reuse a holdout period after inspecting it repeatedly; it becomes research data.
- Do not promote a candidate that depends on one symbol, one regime, or a small number of trades.
- Do not relax hard-risk limits to improve a backtest.
- Do not force trades to satisfy a desired position count.
- Do not use raw Kelly sizing until a stable, sufficiently large, regime-specific sample exists.
- Do not merge several behavior changes without ablation evidence.
- Prefer shadow comparison against the current policy before changing paper authority.
- Keep `/paper/self-check` as the single routine post-deploy test. Open individual diagnostics only when `failing_components` identifies them.

## Current Gate

Until the architecture audit and shadow-decision path are complete:

- freeze new wrappers, watchdogs, starter valves, and one-off threshold exceptions;
- allow only urgent operational repairs and the testing/refactor foundation;
- treat the existing performance audit V2 as advisory research;
- do not promote new policy values from the research lab without forward paper evidence.

The mandatory exact-head Change Safety Audit applies in addition to these temporary rebuild constraints. It does not authorize any cutover otherwise blocked by Issue #82 or the architecture migration plan.
