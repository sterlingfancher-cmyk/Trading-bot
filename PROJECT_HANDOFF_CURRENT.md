# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-10 after PR #28 merge  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Latest runtime-code head covered: `a02d893c4682905f05508bd03b5ed4d02fc2143b`  
Canonical paper service: `https://web-production-e1796.up.railway.app`

This file is the authoritative continuation point. Older `PROJECT_HANDOFF_*` files are historical context only unless this file explicitly references them.

## Executive Status

The project is in the **Stable Core + Performance Lab** phase.

The historical accounting incident is resolved by a deliberate clean paper-accounting epoch. The project must **not** return to repeated historical reconstruction attempts.

The current objective remains:

**Simplify the plumbing, preserve the performance engine.**

Preserve the scanner, broad momentum/discovery path, opening-surge/breakout participation, regime logic, long/short capability, provider protections, and risk framework unless a demonstrated defect requires a targeted change.

Runtime remains **paper-only**. Rules remain the sole execution authority. ML, MAE/MFE optimization, crypto/multi-asset ranking, LONA, adaptive policies, and other Performance Lab work remain shadow/research-only until explicit promotion gates are satisfied.

## One Routine Operator Test

Use only this routine test unless it identifies a specific blocker:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

Use the forensic form only when specifically needed:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Do not return to a daily workflow requiring multiple bootstrap/accounting/debug URLs.

## Historical Recovery Decision — Final

The decisive 2026-08-10 audit showed:

- historical journal rows: `147`
- semantic-deduplicated execution rows: `34`
- entry rows: `5`
- exit/partial-exit rows: `29`
- unresolved coverage issues: `23`
- `trusted_recovery_candidate: false`

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

PR #26:

- archived contaminated state/journal/backups before mutation
- established clean `$10,000` cash/equity
- removed carried-over positions/trades/P&L
- replaced stale fallback backups so old contamination could not resurrect
- rotated journal/snapshot state into the new epoch
- preserved canonical ledger cleanliness
- converted the failed historical journal to archived forensic evidence
- made a rigorously verified zero-trade epoch a valid accounting baseline
- reset ML/MAE-MFE promotion evidence to require clean forward lifecycle data
- deliberately left the runtime on a clean-epoch validation hold

Migration writes clean fallback backups first and swaps primary `state.json` last so migration failure leaves the old halted primary recoverable.

## Verified Post-Cutover Railway Audit — 2026-08-10 13:36:18 CDT

The clean epoch was successfully established.

### Account

- cash: `$10,000`
- equity: `$10,000`
- positions: none
- realized today: `$0`
- unrealized P&L: `$0`

### Epoch

- `epoch_id: stable-paper-v1-20260810-clean01`
- `clean_start: true`
- `zero_trade_baseline: true`
- `historical_evidence_archived: true`
- `historical_recovery_decision: clean_epoch`

### Accounting integrity

- `coverage_complete: true`
- `baseline_type: clean_zero_trade_epoch`
- coverage issues: `0`
- economic issues: `0`
- reconstructed cash: `$10,000`
- reconstructed equity: `$10,000`

### Canonical ledger

- `chain_valid: true`
- `authoritative_for_new_executions: true`
- `row_count: 0`
- `current_epoch_rows: 0`
- `current_epoch_id: stable-paper-v1-20260810-clean01`

### Historical journal

- status: archived
- recovery decision complete
- `trusted_recovery_candidate: false`

The contaminated account did not reappear. The clean-epoch cutover therefore passed its baseline verification.

## Findings From the Post-Cutover Audit

Two important implementation issues were identified before releasing Stable Paper:

1. The performance-risk layer treated **any** `risk.halted` state as a hard performance/self-defense halt. The clean-epoch administrative validation hold was therefore incorrectly reported as loss-driven self-defense despite `0%` loss and drawdown.
2. The prior accounting reconciler was long-lot oriented and could not safely validate a future legitimate short lifecycle. Stable Paper must not resume with a long/short strategy while accounting silently ignores short rows.

The compact audit also used the combined market-data/path/ML section status as `market_data.status`, causing the clean-forward MAE/MFE evidence gate to look like a provider failure. Provider request accounting itself can have a one-request in-flight snapshot gap; that is distinct from ML promotion readiness.

## PR #28 — Stable Paper Post-Cutover Release Guards

Merged runtime commit:

`a02d893c4682905f05508bd03b5ed4d02fc2143b`

Both repository workflows passed, including the exact Gunicorn startup smoke.

PR #28 adds the release-critical protections required before forward Stable Paper validation:

### Bidirectional long/short accounting

The paper reconciler now models the runtime's actual cash/margin semantics:

- long entry reserves entry notional
- long exit/partial exit releases matched sale proceeds
- short entry reserves entry notional as margin
- short exit/partial exit releases matched margin plus realized P&L
- unmatched exits cannot create synthetic cash
- unknown execution side fails accounting coverage instead of silently defaulting to long

This preserves short capability while making short accounting auditable.

### Execution timestamp semantics

Canonical `record_trade()` rows may store epoch seconds. The accounting boundary now normalizes epoch-second execution times into calendar timestamps so `realized_today` is reconstructed correctly.

### Administrative-halt classification

A clean-accounting validation hold is now classified as an **administrative execution block**, not a loss event. The hold itself remains enforced until the release guard validates it.

### Guarded clean-epoch validation release

The release module may clear **only** the exact `clean accounting epoch validation hold` and only after rechecking:

- paper-only runtime
- correct clean epoch id
- clean-start/zero-trade epoch markers
- archived historical evidence
- `$10,000` cash/equity baseline
- zero positions and state trades
- zero realized/unrealized P&L
- zero loss/drawdown metrics
- healthy authoritative empty canonical ledger aligned to the clean epoch
- bidirectional long/short accounting installed
- complete zero-trade accounting coverage with zero issues
- historical journal decision complete and still untrusted

Any unrelated risk halt is preserved and cannot be cleared by this module.

### Audit/readiness separation

The compact daily audit now distinguishes provider health from clean-forward ML/MAE-MFE evidence readiness instead of labeling the latter as a market-data failure.

### Regression coverage

Focused tests were added for:

- epoch-second timestamp normalization
- unknown-side fail-closed behavior
- complete long + short round-trip accounting
- administrative hold classification without clearing the halt
- proof that an unrelated performance-risk halt cannot be cleared by the clean-epoch release module

## Stable Paper v1 Acceptance Clock

After Railway deploys PR #28 and the routine audit confirms the validation hold is released without any new blocker, begin the Stable Paper v1 acceptance window.

Run the **same Stable Core unchanged** for at least `5` consecutive trading days.

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
- provider accounting remains clean or any snapshot gap is explicitly classified as in-flight rather than unexplained
- cycle ownership remains clean
- risk controls behave as designed
- entry → fill → position → exit → immutable ledger consistency

If defects recur, extend the unchanged evidence window to `7–10` trading days after the defect is corrected.

## Immediate Stable Core Priorities

Do not add new strategy features merely because the account is now clean.

Priority order:

1. Verify the deployed PR #28 runtime with the one normal daily audit.
2. Confirm the clean-epoch administrative validation hold is released and not replaced by any unrelated risk halt.
3. Confirm bidirectional accounting reports healthy before and after the first real long/short lifecycle.
4. Confirm the canonical ledger receives the first new execution with correct epoch id, execution id, and valid hash chain.
5. Establish one authoritative account/position state consistently derived from canonical executions plus current marks.
6. Continue execution-boundary invariants for cash, notional, lot ownership, quantity, duplicate ids, and ledger/state synchronization.
7. Remove/bypass redundant historical execution/persistence wrappers gradually behind regression gates.
8. Remove the temporary clean-epoch migration safety shim only after the new epoch has remained persistent through redeploys/restarts.
9. Keep Stable Core logic frozen during the 5-day acceptance window unless a correctness defect requires repair.

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

## Performance Lab — Preserve, Do Not Promote Yet

Keep alive in parallel:

- ML recommendations/counterfactual research
- MAE/MFE research and future stop/target optimization
- adaptive/multi-asset shadow ranking
- BTC / ETH / SOL research
- LONA independent validation
- alternate regime/participation policies
- walk-forward, Monte Carlo, slippage, commission, and stress testing

Old contaminated/recovery-era rows do not qualify for promotion. Clean-forward evidence must come from the new epoch.

These systems may study what would have improved paper trades, but they must not destabilize Stable Core or obtain execution authority before promotion gates are met.

## Live-Readiness Direction

Evidence-gated sequence:

1. maintain clean accounting truth
2. finish canonical account-state/invariant work
3. freeze Stable Core
4. complete at least 5 unchanged clean paper trading days
5. validate actual entry/exit/sizing/risk behavior from canonical records
6. run live-readiness simulation against broker-state assumptions
7. only then consider a controlled live pilot

Do not automatically choose an arbitrarily tiny live account if it would distort the proven architecture. Determine minimum viable live capital later from the validated sizing/diversification rules.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated historical ledger rows.
- Historical recovery decision is final: **clean epoch**.
- Rules remain sole execution authority.
- ML remains shadow-only.
- Crypto/multi-asset execution remains disabled.
- No risk-threshold weakening merely to create trades.
- Preserve forensic archives before deleting temporary migration components.
- Preserve the performance engine while simplifying accounting/runtime plumbing.
- Any future halt caused by real risk metrics must remain authoritative and must not be cleared by administrative-release code.

## Immediate Continuation Prompt

Start by reading this file, then inspect only the latest normal Railway audit unless it identifies a specific blocker:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

The next question is:

**Did deployed PR #28 safely release the clean-epoch administrative hold while preserving zero-loss accounting integrity, bidirectional long/short accounting, canonical ledger health, and all genuine risk controls?**

If yes, start/continue the unchanged Stable Paper v1 forward-validation clock and focus on canonical account-state/execution invariants. If no, keep execution blocked and fix only the demonstrated correctness issue.