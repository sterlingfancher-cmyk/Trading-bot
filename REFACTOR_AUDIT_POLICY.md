# Continuous Refactor and Code-Review Policy

## Purpose

The trading system must detect structural regressions before they become runtime recursion, conflicting risk behavior, hidden performance loss, or state corruption.

This policy adds three independent controls within one trusted GitHub Actions workflow:

1. a per-update structural review for every Python change;
2. a recurring full-repository architecture audit;
3. a recurring read-only Railway research and self-check snapshot.

The audit is advisory for existing debt and blocking for newly introduced critical debt. It never deletes code automatically, changes strategy parameters, starts a backtest, mutates paper state, or places orders.

## Consolidated Workflow

Workflow:

- `.github/workflows/refactor-audit.yml`

Components:

- `refactor_audit.py`
- `refactor_audit_cli.py`
- `architecture_ownership_registry.json`
- `architecture_contract_validation.py`
- `runtime_research_snapshot.py`

The workflow produces two independent commit statuses on Python updates:

- `refactor-audit`
- `research-snapshot`

## Per-Update Review

The structural job runs for every Python push and pull request. It compares the current tree with the base commit and checks for newly introduced:

- replacements of critical callables;
- overlapping mutation ownership;
- conflicting environment-variable defaults;
- conflicting parameter ownership;
- duplicate route registration;
- import cycles;
- import-time activation and thread creation;
- persistent loops without a safe wait;
- provider-like calls inside loops;
- broad exception suppression;
- duplicate implementations and parallel version families;
- oversized modules and functions.

The per-update gate fails only when the change introduces a new critical finding or violates a registered ownership contract. Existing critical findings remain visible in the report and must be removed through controlled refactoring rather than mass deletion.

## Ownership Contract

The machine-readable registry freezes the current known owners for selected high-risk targets:

- scanner authority;
- entry and rotation authority;
- state persistence;
- entry-quality evaluation;
- paper execution;
- exit management;
- market-data access;
- cycle orchestration;
- route overlaps;
- conflicting environment keys.

During migration:

- removing a legacy owner is allowed and recorded as progress;
- adding an owner to a registered target fails;
- introducing an undeclared route overlap or environment-default conflict fails;
- target future-owner names are descriptive only and receive no runtime authority.

## Scheduled Deep Audit

The full audit runs every Sunday at 12:30 UTC, approximately 7:30 AM Central during daylight time.

A scheduled run has no base comparison. It records the entire architecture surface and reports trends including:

- Python file and line count;
- import graph and cycles;
- module-level call count;
- watchdog and import-time thread count;
- mutation targets and overlapping owners;
- environment and parameter conflicts;
- route overlaps;
- exact duplicate function bodies;
- broad exception suppression;
- high-frequency loops and provider calls inside loops.

JSON and Markdown reports are retained as GitHub Actions artifacts for 30 days.

## Runtime Research Snapshot

The runtime snapshot runs:

- after each qualifying push, following a deployment-settle delay;
- every weekday at 23:15 UTC, approximately 6:15 PM Central during daylight time;
- on manual workflow dispatch.

It performs bounded read-only GET requests for:

- `/paper/self-check`
- `/paper/performance-audit-v2-status`
- `/paper/performance-ablation-v2`
- `/paper/performance-regime-report-v2`
- `/paper/performance-v2-recovery-status`

It does not call authenticated cycle routes, start a backtest, change parameters, mutate state, or place orders.

Its purpose is to preserve forward evidence and research-run state independently of this chat session.

## Severity Model

### Critical

Critical findings include:

- a new replacement of a protected scanner, entry, exit, or order callable;
- a new conflicting default for a protected risk or authority setting;
- a new overlapping owner for a protected callable or hard-risk parameter;
- a Python parse failure;
- an unauthorized owner on a registered architecture target;
- an undeclared route overlap or environment-default conflict.

A newly introduced critical finding fails the per-update audit.

### Warning

Warnings include:

- non-protected mutation overlap;
- duplicate route ownership already recorded in the baseline;
- conflicting non-protected parameter defaults;
- import-time threads;
- high-frequency watchdogs;
- broad exception suppression;
- oversized modules or functions;
- import cycles;
- network/provider calls inside loops.

Warnings require review and create refactor debt, but do not automatically fail a change unless the reviewer determines they can alter trading behavior, state integrity, or resource consumption.

### Informational

Informational findings inventory:

- import-time activation;
- exact duplicate function bodies;
- parallel version families;
- other architecture evidence that may be legitimate but should have one declared owner.

## Required Review for Every Update

Every Python update must answer:

1. Did the repository validator pass?
2. Did the refactor audit introduce a new critical finding?
3. Did the ownership contract report any unauthorized owner?
4. Did mutation-owner counts increase for scanner, entry, state, execution, risk, or route targets?
5. Did the update add another wrapper, watchdog, import-time activation, or hidden callable replacement?
6. Did it introduce a conflicting default or ambiguous percentage unit?
7. Did it increase provider calls, loop frequency, or broad exception suppression?
8. Can the update alter a trading decision?
9. If trading behavior can change, were backtest, walk-forward, cost sensitivity, and forward paper requirements satisfied?

## Relationship to Trading Validation

The structural audit does not replace strategy validation.

Changes to signals, ranking, score, entry, exit, sizing, exposure, capacity, or risk still require:

- baseline-versus-candidate testing;
- walk-forward or untouched holdout testing;
- transaction-cost and slippage sensitivity;
- regime and calendar segmentation;
- ablation when multiple controls change;
- forward shadow or bounded paper evidence;
- `/paper/self-check` after deployment.

Documentation and audit-only changes do not require a trading backtest because they cannot alter decisions.

## Safety Rules

- Never auto-delete a module because static analysis marks it unused.
- Check Gunicorn imports, route registration, import-time activation, `getattr`, `setattr`, and watchdog behavior first.
- Never automatically promote research parameters.
- Never change hard-risk limits to resolve an audit warning.
- Never force trades to satisfy a position-count objective.
- Never hide existing critical findings by changing audit severity without evidence.
- Calibrate false positives in the audit tooling rather than weakening the protected-callable rules.
- Keep reports read-only and free of secrets, credentials, environment values, and paper-state payloads beyond bounded status summaries.

## Baseline and Trend Control

The canonical starting inventory is recorded in `ARCHITECTURE_AUDIT_BASELINE.md`.

Refactoring progress must reduce or hold the following measures:

- critical findings;
- protected callable owners;
- mutation overlaps;
- environment conflicts;
- parameter-owner conflicts;
- route overlaps;
- high-frequency watchdogs;
- broad exception suppression;
- oversized modules and functions.

A refactor is not successful merely because line count decreases. It must preserve paper behavior, pass the repository and structural gates, and satisfy backtest and forward requirements whenever decision output can change.
