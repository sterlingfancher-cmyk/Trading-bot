# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-11 after Stable Paper Day 1 opening audit and PR #30 merge  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Latest runtime-code head covered: `619619418528b584b539ed1d549e64a2ee8fc2ad`  
Canonical paper service: `https://web-production-e1796.up.railway.app`

This file is the authoritative continuation point. Older `PROJECT_HANDOFF_*` files are historical context only unless this file explicitly references them.

## Executive Status

The project is in the **Stable Core + Performance Lab** phase.

The historical accounting incident is resolved by a deliberate clean paper-accounting epoch. Do **not** return to repeated historical reconstruction attempts.

Current objective:

**Simplify the plumbing, preserve the performance engine.**

Preserve the scanner, broad momentum/discovery path, opening-surge/breakout participation, regime logic, long/short capability, provider protections, and risk framework unless a demonstrated correctness defect requires a targeted change.

Runtime remains **paper-only**. Rules remain the sole execution authority. ML, MAE/MFE optimization, crypto/multi-asset ranking, LONA, adaptive policies, and other Performance Lab systems remain shadow/research-only until explicit promotion gates are satisfied.

## One Routine Operator Test

Use only this routine test unless it identifies a specific blocker:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

Use the forensic form only when specifically needed:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Do not return to a daily workflow requiring multiple bootstrap/accounting/debug URLs.

## Historical Recovery Decision — Final

The decisive 2026-08-10 audit showed incomplete historical execution coverage and `trusted_recovery_candidate: false`.

The historical candidate equity around `$14.4k` was rejected because missing entries could not be proven.

**Historical recovery is permanently closed. Do not fabricate missing entries or restart the forensic-recovery loop.**

## PR #24 — Canonical Execution Ledger

Merged runtime commit:

`6e7500a06935bc75a7f44d8ae742cd37b87bc5f6`

Established the forward execution source of truth:

- append-only persistent JSONL execution ledger
- SHA-256 hash chain
- durable `execution_id`
- accounting epoch id on each execution
- execution id/hash propagated into `state.trades`
- hook at canonical `record_trade`
- fail-safe halt if ledger durability/integrity fails
- ledger health in the routine daily audit

It is authoritative for new executions and never claimed to reconstruct missing historical rows.

## PR #26 — Clean Accounting Epoch

Merged runtime commit:

`73fa71d662cd7e325373b8f3f1e1dec1cd1e5524`

Target epoch:

`stable-paper-v1-20260810-clean01`

Starting paper capital:

`$10,000`

PR #26 archived contaminated state/journal/backups, established a clean `$10,000` account, removed carried-over positions/trades/P&L, replaced stale fallback backups, rotated journal/snapshot state, preserved the new canonical ledger, and deliberately left the runtime on a validation hold.

The 2026-08-10 post-cutover Railway audit verified:

- cash/equity exactly `$10,000 / $10,000`
- no positions
- zero realized/unrealized P&L
- complete accounting coverage
- zero coverage/economic issues
- canonical ledger healthy, authoritative, empty, and epoch-aligned
- historical journal archived
- contaminated account did not reappear

## PR #28 — Stable Paper Post-Cutover Release Guards

Merged runtime commit:

`a02d893c4682905f05508bd03b5ed4d02fc2143b`

Both repository workflows passed, including the exact Gunicorn startup smoke.

PR #28 added:

- bidirectional long/short accounting using the runtime cash/margin semantics
- unmatched-exit protection for both directions
- unknown execution side fails accounting coverage instead of silently defaulting to long
- epoch-second execution timestamp normalization for `realized_today`
- administrative-halt classification so a clean validation hold is not mislabeled as a loss event
- guarded release that can clear **only** the exact clean-accounting validation hold after re-verifying the clean baseline
- provider-health reporting separated from ML/MAE-MFE promotion readiness
- focused regression tests

The clean-accounting validation hold was released at:

`2026-08-10 16:11:51 CDT`

No genuine risk halt was present.

## Stable Paper Day 1 — 2026-08-11 08:50:42 CDT Audit

This is the first clean forward execution evidence after the new epoch and release.

### Account

- cash: `$8,400.00`
- equity: `$10,005.39`
- open position: `CLSK`
- realized today: `$0.00`
- unrealized P&L: `$5.39`

### Accounting integrity

- model: `bidirectional_margin_v1`
- long/short support: `true`
- `coverage_complete: true`
- coverage issues: `0`
- economic issues: `0`
- ignored trade rows: `0`
- reconstructed cash: `$8,400.000020`
- reconstructed equity: `$10,005.387216`

Stored and reconstructed account values agree within normal rounding tolerance.

### Canonical execution ledger

- `chain_valid: true`
- `authoritative_for_new_executions: true`
- current epoch id: `stable-paper-v1-20260810-clean01`
- current epoch rows: `1`
- total ledger rows: `1`

The first clean forward entry therefore reached the canonical ledger successfully.

### Provider accounting

- requests: `4,622`
- classified terminal outcomes: `4,622`
- in-flight/unclassified: `0`
- provider circuit open: `false`
- status: `pass`

### Risk

- halted: `false`
- self-defense active: `false`
- intraday drawdown: `0%`
- net daily loss: `0%`
- status: `pass`

### Clean-forward research evidence

- post-epoch valid exact lifecycle rows: `1`
- promotion evidence eligible: `true`
- ML evidence status: `pass`

This does **not** grant ML execution authority. It only means the clean-forward evidence gate has begun receiving valid lifecycle data.

### Only remaining warning in this audit

`scanner.entries_count` was `null`, producing `entry_count_missing` even though the bot had clearly executed a real clean entry and the canonical ledger showed one execution.

This was proven to be an observability/reporting gap rather than a trading-path failure.

## PR #30 — Audit Entry-Count Reporting Fix

Merged runtime commit:

`619619418528b584b539ed1d549e64a2ee8fc2ad`

Both repository validation workflows passed, including exact Gunicorn startup smoke.

PR #30 is **reporting-only**:

- if scanner `entries_count` is missing, it uses the already-persisted `auto_runner.last_result.entries` list for the latest-cycle count
- it does not overwrite an explicit scanner-provided count
- if no fallback exists, it leaves the warning in place instead of fabricating a count
- it clears the obsolete `entry_count_missing` next-action only when the fallback is actually available
- regression tests cover all three cases

PR #30 changes no scanner logic, signals, thresholds, sizing, risk limits, execution behavior, live authority, or ML authority.

**PR #30 does not reset the Stable Paper validation clock.**

## Stable Paper v1 Acceptance Clock

Day 1 is **2026-08-11**.

Run the same Stable Core behavior unchanged for at least `5` consecutive trading days. Reporting-only observability corrections do not reset the clock. Strategy, execution, accounting-semantic, sizing, or risk-behavior changes generally do reset the unchanged-evidence window unless they are required to correct a safety/correctness defect.

Minimum acceptance requirements:

- no state corruption
- no impossible accounting
- no duplicate executions
- canonical ledger hash chain remains valid
- every state execution maps to a canonical `execution_id`
- account/position state reconciles with canonical execution events
- long and enabled short lifecycle accounting remains complete
- no unexplained startup failure
- no manual state repair
- one compact daily audit per trading day
- provider accounting remains clean or any snapshot gap is explicitly classified as in-flight
- cycle ownership remains clean
- risk controls behave as designed
- entry → fill → position → exit → immutable ledger consistency

If a correctness defect occurs, repair it and extend/restart the unchanged evidence window as appropriate. If only reporting/observability is corrected without trading-behavior changes, preserve the clock.

## Immediate Stable Core Priorities During the 5-Day Window

Do not add new strategy features merely because the account is now clean.

Priority order:

1. Continue the one-link daily audit each trading day.
2. Verify PR #30 reporting after Railway deploys; `entries_count` should no longer be null when latest-cycle runner entries are available.
3. Observe the CLSK lifecycle through management and eventual exit; verify entry → position → exit → canonical ledger/accounting consistency.
4. Confirm bidirectional accounting remains healthy before and after the first legitimate short lifecycle if one occurs naturally under existing rules.
5. Confirm every new execution increases the canonical ledger without chain or epoch mismatch.
6. Continue account-state/execution-invariant work only if it can be done without changing Stable Core trading behavior during the acceptance window.
7. Remove/bypass redundant historical wrappers only behind regression gates and only if the change cannot alter trading decisions during the clock.
8. Remove the temporary clean-epoch migration safety shim only after the epoch has remained persistent through redeploys/restarts.

## Strategy / Risk Components to Preserve

Preserve unless evidence identifies a specific defect:

- rules-engine execution authority
- broad-market momentum discovery
- canonical bounded detailed scanner
- scanner ownership / recursion-safety contract
- opening-surge and breakout participation logic
- long/short regime capability
- provider timeout/circuit/hygiene protections
- ORLA/static no-data hygiene
- persistent Railway volume
- cycle-completion contract
- after-hours market-closed skipping
- paper-only execution boundary

Risk boundaries remain:

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`

Do not loosen these merely to create trades or accelerate validation.

Historical scanner/discovery bounds worth preserving unless evidence says otherwise:

- retained discovery candidates: `160`
- broad-momentum slots: `80`
- base/fallback slots: `25`
- detailed-scanner input: `110`
- discovery cache: `900` seconds

## Performance Lab — Preserve, Do Not Promote Execution Authority Yet

Keep alive in parallel:

- ML recommendations/counterfactual research
- MAE/MFE research and future stop/target optimization
- adaptive/multi-asset shadow ranking
- BTC / ETH / SOL research
- LONA independent validation
- alternate regime/participation policies
- walk-forward, Monte Carlo, slippage, commission, and stress testing

Clean-forward evidence may now be collected and evaluated, but these systems must not destabilize Stable Core or obtain execution authority before explicit promotion gates are met.

## Live-Readiness Direction

Evidence-gated sequence:

1. maintain clean accounting truth
2. complete the unchanged Stable Paper validation window
3. validate actual entry/exit/sizing/risk behavior from canonical records
4. finish canonical account-state/invariant work
5. run live-readiness simulation against broker-state assumptions
6. only then consider a controlled live pilot

Do not automatically choose an arbitrarily tiny live account if it would distort the proven architecture. Determine minimum viable live capital later from validated sizing/diversification rules.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated historical ledger rows.
- Historical recovery decision is final: **clean epoch**.
- Rules remain sole execution authority.
- ML remains shadow-only for execution.
- Crypto/multi-asset execution remains disabled.
- No risk-threshold weakening merely to create trades.
- Preserve forensic archives before deleting temporary migration components.
- Preserve the performance engine while simplifying accounting/runtime plumbing.
- Any future halt caused by real risk metrics remains authoritative and must not be cleared by administrative-release code.

## Immediate Continuation Prompt

Start by reading this file, then inspect only the latest normal Railway audit unless it identifies a specific blocker:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

The current question is no longer whether the clean epoch works. It does.

The current question is:

**Does Stable Paper remain internally consistent through each new clean execution and position lifecycle for at least five consecutive trading days without strategy/risk behavior changes?**

If yes, continue the acceptance clock. If a genuine accounting, execution, persistence, startup, or risk correctness defect appears, fix only that defect and determine whether the unchanged-evidence window must restart.
