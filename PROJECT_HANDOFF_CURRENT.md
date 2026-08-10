# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-10 after PR #26 merge  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Latest runtime-code head covered: `73fa71d662cd7e325373b8f3f1e1dec1cd1e5524`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway deployment of PR #26: **not yet verified in this handoff**

This file is the authoritative continuation point. Older `PROJECT_HANDOFF_*` files are historical context only unless this file explicitly references them.

## Executive Status

The project remains in the **Stable Core + Performance Lab** phase.

The historical accounting-recovery decision is now **resolved**. The live compact audit proved that the older mirrored trade journal cannot establish complete historical entry/exit coverage. We are therefore **not continuing historical repair loops** and are intentionally moving to a clean paper-accounting epoch.

The objective remains:

**Simplify the plumbing, preserve the performance engine.**

Do not strip the trading logic down to a generic or overly conservative system merely to gain stability. Preserve the scanner, momentum/discovery, opening-surge/breakout participation, regime logic, risk framework, and other strategy components associated with the stronger paper periods unless a specific defect is demonstrated.

The runtime remains **paper-only**. Rules remain the sole execution authority. ML, MAE/MFE optimization, crypto/multi-asset ranking, LONA work, and other Performance Lab systems remain shadow/research-only.

## One Routine Operator Test

Use only this routine test unless a demonstrated blocker requires a targeted diagnostic:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

Full forensic output only when specifically needed:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Do not return to a normal workflow requiring multiple bootstrap/accounting/debug URLs. Keep the routine audit compact and iPhone copy/paste friendly.

## Decisive Live Audit — 2026-08-10 13:11:55 CDT

The first deployed audit after PR #24 produced the evidence required by the handoff.

### Contaminated account still present

- cash: `-1588422.0876077376`
- equity: `-1559883.6`
- positions: `AI`, `CRWD`, `QQQ`
- realized today: `-15647.57`
- unrealized P&L: `4707.06`
- risk halt: active
- halt reason: `absolute daily equity loss halt (3.00%)`
- reported intraday drawdown: `100%`
- reported net daily loss: `100%`

These values are contaminated bookkeeping and are **not valid strategy-performance evidence**.

### `state.trades` reconstruction remained incomplete

- `coverage_complete: false`
- coverage issues: `20`
- ignored rows: `20`
- economic issue count reported by the combined accounting audit: `20`
- bounded reconstructed cash: `14386.326092`
- bounded reconstructed equity: `17997.655015`

These reconstructed values are not trusted because execution coverage is incomplete.

### Historical journal recovery candidate — decisive result

- journal rows: `147`
- semantic-deduplicated execution rows: `34`
- entry rows: `5`
- exit/partial-exit rows: `29`
- coverage issues: `23`
- `coverage_complete: false`
- economic issues after matched-exit protection: `0`
- candidate cash/equity: `14431.497124`
- `trusted_recovery_candidate: false`

**Decision: historical recovery is rejected.**

The `$14,431.50` candidate is not carried into the new account because the journal cannot prove the missing entries. Do not fabricate entries or treat that candidate as real paper equity.

### New canonical execution ledger — healthy before cutover

- `chain_valid: true`
- `authoritative_for_new_executions: true`
- `row_count: 0`
- `current_epoch_rows: 0`
- pre-cutover epoch id: `legacy-pre-stable-core`

This is the ideal cutover point because no post-ledger executions need migration.

### Provider observation from the same audit

- provider requests: `60`
- classified terminal outcomes: `59`
- provider circuit open: `false`

The one-request accounting mismatch is secondary to the accounting reset, but it must be clean before Stable Paper v1 can pass its acceptance gate.

## Historical Accounting Incident — Root Cause

Two confirmed defects drove the repair work:

1. **Side-first reconstruction.** Canonical rows store `action` separately from `side`. A row such as `action="exit", side="long"` was previously interpreted as a buy because `side="long"` was consulted first. PR #21 made `action` authoritative.
2. **Unmatched exits creating synthetic cash.** Once action semantics were corrected, unmatched/duplicate exits could still credit proceeds without a reconstructed lot. PR #22 changed reconstruction so proceeds are credited only for quantity proven to exist.

Those bugs are corrected, but neither correction can manufacture the missing historical entry rows. That is why the journal-recovery decision was necessary.

## PR #24 — Canonical Execution Ledger

Merged runtime commit:

`6e7500a06935bc75a7f44d8ae742cd37b87bc5f6`

PR #24 established the forward execution source of truth:

- append-only JSONL ledger on the persistent volume
- SHA-256 hash chain
- durable `execution_id` for each new entry/exit/partial exit
- accounting epoch id attached to each event
- ledger hash/id propagated into the corresponding `state.trades` row
- direct hook at the canonical `record_trade` boundary
- hard fail-safe if the ledger cannot be written or verified
- compact ledger health in the one-link audit

It is authoritative for **new** executions only and never claimed to recover missing historical rows.

## PR #26 — Clean Accounting Epoch

PR #26 passed both repository CI workflows, including the exact Gunicorn startup smoke, and was squash-merged as:

`73fa71d662cd7e325373b8f3f1e1dec1cd1e5524`

Target accounting epoch:

`stable-paper-v1-20260810-clean01`

Starting paper capital:

`$10,000`

The clean-epoch migration is intentionally guarded and one-time. It runs only when:

- runtime is paper-only
- the known contaminated halted state is present
- historical journal recovery is explicitly untrusted
- canonical execution ledger is healthy and still empty

### What PR #26 does

1. Archives the persistent state directory before mutation and writes a forensic manifest with file hashes and the recovery evidence.
2. Builds a fresh `$10,000` paper state with zero positions, zero trades, zero realized P&L, and zero unrealized P&L.
3. Establishes the explicit new accounting epoch id.
4. Replaces active state fallback backups, including `state_backup_largest.json`, so stale contaminated backups cannot resurrect the old state.
5. Rotates the mirrored trade journal and its backup into the clean epoch.
6. Rotates the snapshot archive so its monotonic-history guard cannot restore contaminated trade history.
7. Keeps the canonical execution ledger clean and associates future events with the new epoch.
8. Treats the failed historical journal as archived forensic evidence after the decision rather than a recurring recovery warning.
9. Makes a rigorously verified zero-trade clean epoch count as complete accounting coverage.
10. Prevents action-semantics recovery from replaying historical reconstruction after the clean epoch exists.
11. Resets MAE/MFE/ML promotion evidence to require new clean forward lifecycle evidence.
12. Leaves the system on a hard **clean accounting epoch validation hold** after migration.

### Migration failure safety

The migration was hardened before merge:

- no nested `trade_journal.mirror_state()` while journal/state locks are held
- backup copies use a portable durable fsync path
- all clean fallback backups are written first
- the primary `state.json` is atomically swapped **last**

If backup preparation fails, the old hard-halted primary state remains intact and the migration can be retried instead of leaving a half-migrated account.

The temporary migration safety shim can be removed after the clean epoch is deployed and validated.

## Expected First Audit After PR #26 Deploys

Do **not** clear the validation hold before checking the normal one-link audit.

Expected clean baseline:

- compactor version: `final-daily-audit-compactor-2026-08-10-v3-clean-accounting-epoch`
- account cash: about `$10,000`
- account equity: about `$10,000`
- positions: none
- realized today: `$0`
- unrealized P&L: `$0`
- accounting epoch id: `stable-paper-v1-20260810-clean01`
- `clean_start: true`
- `zero_trade_baseline: true`
- historical recovery decision: `clean_epoch`
- historical evidence archived: `true`
- validation hold: `true`
- accounting coverage: complete
- accounting baseline type: `clean_zero_trade_epoch`
- coverage issue count: `0`
- journal status/disposition: archived / decision complete
- canonical ledger: chain valid, authoritative, row count `0`, current epoch rows `0`, current epoch id equal to the clean epoch id
- risk halted: `true`
- halt reason: `clean accounting epoch validation hold`
- drawdown/loss metrics: reset to normal clean-baseline values
- ML/MAE-MFE promotion remains blocked for new clean forward evidence

The overall audit may remain non-pass solely because the deliberate validation hold and clean-evidence gate are active. That is expected. What is **not** acceptable is contaminated cash/equity, old positions/trades resurfacing, accounting coverage issues, ledger mismatch, or stale loss/drawdown values.

## Release Rule for the Validation Hold

Do not manually clear the hold merely because the deploy succeeded.

Release requires the post-deploy one-link audit to prove:

- clean `$10,000` account baseline
- no positions/trades carried over
- clean epoch id correct
- forensic archive recorded
- active backups/journal/snapshot no longer reintroduce old history
- accounting coverage complete with zero issues
- canonical ledger healthy and epoch-aligned
- no unexplained state/persistence error

If any of those fail, keep the hold and fix the specific persistence/accounting defect.

## Important Next Stable Core Work Before the 5-Day Clock

After the clean baseline is verified, continue the Stable Core refactor rather than adding new strategy features.

Priority order:

1. Verify PR #26 deployment with the one routine audit.
2. Keep the validation hold until the clean baseline passes.
3. Establish one authoritative account/position state derived consistently from canonical execution events plus current marks.
4. Add execution-boundary invariants for cash, notional, lot ownership, quantity, duplicate execution ids, and ledger/state synchronization.
5. Resolve a known accounting limitation before a bear-regime short can participate in Stable Paper v1: the current historical long-lot reconciler deliberately marks short lifecycle rows as unsupported. Either add canonical short-lot accounting or explicitly keep paper shorts blocked until that accounting path is proven. Do **not** silently ignore short rows.
6. Recheck provider request accounting; the latest audit had `60` requests vs `59` classified outcomes.
7. Remove/bypass redundant historical execution-path wrappers gradually with regression gates.
8. Remove the temporary clean-epoch migration shim after the epoch is established and proven persistent.
9. Only then release the validation hold and start the Stable Paper v1 acceptance clock.

## Stable Paper v1 Acceptance Gate

Run the **same Stable Core unchanged** for at least `5` consecutive trading days after the validation hold is released.

Minimum acceptance requirements:

- no state corruption
- no impossible accounting
- no duplicate execution
- canonical hash chain remains valid
- every state execution maps to a canonical `execution_id`
- account/position state reconciles with the canonical ledger
- long and any enabled short lifecycle accounting is complete
- no unexplained startup failure
- no manual state repair
- one compact daily audit per day
- provider request accounting clean
- cycle ownership clean
- risk controls behave as designed
- entry → fill → position → exit → immutable ledger consistency

If defects recur, prefer a longer `7–10` day unchanged evidence window.

## Strategy / Risk Components to Preserve

Do not simplify away the performance engine merely for convenience.

Preserve unless evidence identifies a specific defect:

- rules-engine execution authority
- broad-market momentum discovery
- canonical bounded detailed scanner
- scanner ownership / recursion-safety contract
- opening-surge and breakout participation logic
- provider timeout/circuit/hygiene protections
- ORLA/static no-data hygiene
- persistent Railway volume
- cycle-completion contract
- after-hours market-closed skipping
- paper-only execution boundary

Initial risk boundaries remain:

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum account risk per trade at configured stop: `2.0%`

Do not loosen those merely to manufacture trades or accelerate validation.

Historical scanner/discovery bounds worth preserving unless later evidence says otherwise:

- retained discovery candidates: `160`
- broad-momentum slots: `80`
- base/fallback slots: `25`
- detailed-scanner input: `110`
- discovery cache: `900` seconds

## Performance Lab — Preserve, Do Not Promote Yet

Keep the following systems and development paths alive in parallel:

- ML recommendations/counterfactual research
- MAE/MFE research and future stop/target optimization
- adaptive/multi-asset shadow ranking
- BTC / ETH / SOL research
- LONA independent validation
- alternate regime/participation policies
- walk-forward, Monte Carlo, slippage, commission, and stress testing

They may evaluate what would have improved actual paper trades, but they must not destabilize the Stable Core or obtain execution authority before promotion gates are met.

Old contaminated/recovery-era MAE/MFE rows must not qualify for future promotion. PR #26 changes the forward block to the clean-accounting-epoch evidence gate.

## Live-Readiness Direction

The evidence-gated sequence is:

1. establish and verify clean accounting truth
2. finish canonical account-state/invariant work
3. freeze Stable Core
4. complete at least 5 unchanged clean paper trading days
5. validate actual entry/exit/sizing/risk behavior from canonical records
6. run live-readiness simulation against broker-state assumptions
7. only then consider a controlled live pilot

Do not default automatically to an extremely small live account if it would distort the final strategy architecture. Determine minimum viable live capital from the proven Stable Core sizing/diversification rules at that later stage.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated historical ledger rows.
- Historical journal recovery decision is final: **clean epoch**, not more reverse-engineering.
- Clean-epoch validation hold remains until the post-deploy baseline audit passes.
- Rules remain sole execution authority.
- ML remains shadow-only.
- Crypto/multi-asset execution remains disabled.
- No risk-threshold weakening merely to create trades.
- Preserve forensic archives before removing any temporary migration components.
- Preserve the performance engine while simplifying accounting/runtime plumbing.

## Immediate Continuation Prompt

Start by reading this file, then inspect **only** the latest normal Railway audit unless it identifies a specific blocker:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

The next question is no longer whether historical recovery is possible. That decision is complete.

The next question is:

**Did PR #26 establish a persistent clean `$10,000` epoch with zero carried-over trades/positions, complete zero-trade accounting coverage, an empty healthy epoch-aligned canonical ledger, and only the intentional validation hold remaining?**

If yes, proceed to authoritative account-state/execution-invariant work and controlled validation-hold release. If no, keep the hold and fix only the demonstrated persistence/accounting blocker.
