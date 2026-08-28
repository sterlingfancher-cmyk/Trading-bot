# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-08-28 12:05 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Current runtime code baseline: `54df8c9edf43af645b5abac4f6d93c262aeeff37` (squash merge of PR #134)  
Current `main` before this handoff refresh: `1600dd0e5cdc4e162a587c0e6478dd1f9f95eb72`  
Active stability/accounting issue: Issue #126

## Communication and Continuity

Keep Trading-bot progress updates in the currently active ChatGPT conversation until the user intentionally starts a new one. Before any intentional chat transition, refresh this handoff with the exact repository/runtime boundary so the next conversation can continue without reconstructing history.

After every material finding, bug fix, PR, merge, authoritative runtime validation, blocker, accounting/risk boundary change, or issue closure, update this file. The user wants to be as hands-off as possible for routine stability work: investigate, fix, test, merge bounded safe repairs, validate deployment, and notify after meaningful progress. Escalate only decisions/actions that genuinely require the user.

## Standing Safety / Authority Boundaries

- Paper-only unless separately authorized.
- Rules engine remains sole execution authority; ML/AI remains shadow-only.
- Never delete, edit, relabel, truncate, or fabricate immutable canonical execution-ledger rows.
- Never manually clear a lifecycle/risk halt merely to make an audit pass.
- Never rewrite `day_peak_equity`, risk-day history, account history, or historical accounting state merely to make an audit pass.
- Do not casually call `/paper/run`; prefer existing automated read-only runtime snapshots/audits.
- Do not change strategy logic, signal/participation thresholds, sizing policy, hard-risk thresholds, live authority, or ML execution authority as part of bug/stability repair without separate authorization.
- Historical corrections must use exact-evidence successor accounting with archived evidence and validation hold, never immutable-history edits.
- Every relevant code repair must pass exact-head Change Safety Audit, Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit, exact Gunicorn smoke, and affected focused invariant suites before automatic merge.

## Issue #126 — Root Cause and Prospective Containment

The original defect was a re-entrant legacy accounting read during SLS full-exit processing. State deleted SLS, then `set_cooldown()` re-entered accounting before the new canonical row was mirrored into state, allowing the closed SLS position to be reconstructed from the verified snapshot. That resurrected position later generated an impossible SLS partial exit.

PR #127 (`71c3e0777f82f3b1521b3ab17df53a25fb1d91d1`) prospectively contained that failure for successor generations v3+ under validation hold: legacy accounting reconciliation remains observational/fail-closed and may not auto-repair cash/positions during that in-flight window. The existing contaminated v3 state and immutable ledger were deliberately not rewritten.

PR #128 (`4b3c4aa8e4cd0fb9203a95bb80091060b24d28b2`) added the exact-evidence v3→v4 successor migration. It requires the proven v3 baseline, exact known v3 execution signatures, immutable hash-valid canonical history, exact ordering, deterministic replay excluding only the proven invalid SLS partial, archival evidence, validation hold, and exact preservation of risk/history/canonical ledger.

Known original v3 rows from the 45-row proof boundary:
1. Valid SLS full exit `9ab93335faff4e3293d24ebe0bad4e87`.
2. Valid DHR partial exit `26702f252870490c8f1ddab86ce794f5`.
3. Proven invalid re-entrant SLS partial `90b22aad76074031906e0c6459dfa0bc`, retained immutably but excluded from successor economics only when its exact signature remains proven.

## 2026-08-28 Morning Repair — PR #134

The remaining verifier defect was numeric price comparison against canonical ledger values serialized with `round(price, 6)`. Repo-agent attempts #129-#133 were rejected/closed unmerged because their generated file replacement diffs were destructive. No unsafe replacement was merged.

A direct bounded repair was created on `fix/issue126-price-serialization-20260828`:
- production diff exactly one line: `PRICE_TOLERANCE = 1e-9` -> `PRICE_TOLERANCE = 5e-6` in `verified_v3_successor_epoch_migration.py`;
- added `tests/test_verified_v3_signature_checks.py` proving an in-bound serialization delta passes only with exact identity/event hash, an out-of-bound price fails, and event-hash mismatch remains fail-closed.

PR #134 exact head `c3cef758d1e2a0fdcd414168402c3cbd6b5fd585` passed every required exact-head gate, including Change Safety impact-aware regressions/core invariant suite, Repository Safety/Performance, Architecture Debt, full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research audit, focused Stable Paper regressions, and both exact Gunicorn startup smokes. It was squash-merged automatically as runtime code baseline `54df8c9edf43af645b5abac4f6d93c262aeeff37`.

Both Railway deployment contexts and the post-merge repository/refactor validations are green.

Fresh Splendid bootstrap evidence after deployment proves the price repair worked: all three previously known v3 rows now pass every exact check — ledger index, execution ID, epoch, action, symbol, side, quantity, price, and immutable event hash.

## 2026-08-28 Midday Forensic Classification — Canonical Row 46

Fresh automated Splendid snapshot evidence from workflow run `33181093054` / runtime artifact `9689875237` proves the fourth v3 row is not another SLS artifact. It is an exact DHR full-exit row:
- ledger index `45` (46th canonical row);
- execution ID `ae9d82d3d25748459f37842679d501cd`;
- epoch `stable-paper-v3-20260825-successor01`;
- action `exit`;
- symbol/side `DHR` / `long`;
- shares `0.36230183`;
- price `203.039993`;
- exit reason `stop_loss`;
- event hash `0a3af37e3f69477acbc49a29454a8cd377d509186e3c60fa53aa3fe0ae3592b8`;
- recorded local `2026-08-27 09:21:47 CDT`.

The canonical ledger remains parse-clean/hash-valid with exactly 46 rows and exactly four v3 rows. Row 46 is ordered after the original valid SLS full exit, valid DHR partial, and invalid re-entrant SLS partial.

The verified v3 baseline DHR quantity is `0.540748758`. The valid DHR partial row exits `0.17844717`; active accounting reconstruction after the three mirrored state-trade rows shows the remaining DHR quantity as `0.3623017583401764` at entry `216.9600067138672`. Canonical row 46 quantity `0.36230183` therefore closes the reconstructed remainder within the existing exact migration `QTY_TOLERANCE`.

The current persisted state proves the row-46 economic effect was never mirrored:
- current cash `13483.47647864577` equals the v3 baseline plus the valid SLS full-exit proceeds, valid DHR partial proceeds, and invalid SLS partial proceeds, but excludes the DHR row-46 exit proceeds;
- DHR is still open in state;
- `state.trades` still contains exactly the original three v3 rows and does not contain row 46;
- active accounting reconstruction remains DHR-only after ignoring the invalid SLS partial.

`canonical_execution_ledger.py` deliberately appends the immutable canonical row before invoking the prior `record_trade()` state mirror. The evidence therefore classifies row 46 as a **valid canonical-only DHR full exit whose state/cash mirror did not complete**, rather than as a second invalid execution artifact.

Successor-recovery rule is now exact:
- retain all 46 canonical rows immutably;
- replay the valid SLS full exit, valid DHR partial, and valid DHR full exit;
- exclude only invalid SLS partial execution `90b22aad76074031906e0c6459dfa0bc` from successor economics;
- require the pre-cutover state to prove row 46 is absent from `state.trades`, DHR remains exactly at the reconstructable remainder, and row-46 cash proceeds are absent;
- the deterministic v4 successor projection should therefore have **no open positions**;
- preserve validation hold and the lifecycle halt through cutover until clean active-v4 evidence independently proves any release is safe.

A new guarded repo-agent repair was triggered from Issue #126 at midday with those exact requirements. Repo-agent workflow run `33192730802` is the active bounded repair. It must abort if it produces a truncated/replaced migration file or unrelated changes. Any resulting PR must be exact-diff reviewed and pass the complete mandatory exact-head gate suite before automatic merge.

## Current Authoritative Splendid Runtime — 2026-08-28 Midday Evidence

Latest automated read-only runtime snapshot:
- application bootstrap: ready/delegating; no bootstrap error;
- runner: PASS, no active error; latest successful run `2026-08-28 09:34:57 CDT`;
- canonical ledger: PASS, append-only/hash-valid, 46 rows, 4 current-v3 rows;
- account cash: `13483.47647864577`;
- account equity: approximately `13602.08`;
- active state positions: `DHR`, `SLS`;
- active state trade rows: 3;
- accounting integrity: WARN with exactly one coverage issue and one economic issue, both the known invalid SLS partial;
- reconstructed clean state from mirrored state trades remains DHR-only;
- market data: PASS; 103 classified terminal outcomes, zero in-flight/unclassified requests, provider circuit clear;
- state persistence/bootstrap diagnostics healthy;
- fresh-day baseline: PASS, date `2026-08-28`, day start/peak approximately `13606.02`, reset not pending;
- risk: intentionally FAIL because `canonical execution lifecycle integrity halt` remains active; intraday drawdown approximately `0.029%`;
- validation hold remains active;
- no strategy/sizing/risk-threshold/live/ML authority was changed.

The overall audit remains FAIL because the successor accounting repair has not yet been applied, not because runner, market data, canonical hash chain, bootstrap, or fresh-day initialization are unhealthy.

## Immediate Next Action

Inspect the repo-agent output for run `33192730802`. Accept only a bounded migration/test repair that encodes the exact 46-row/four-v3-row evidence, requires row 46 to be canonical-only and economically unapplied in pre-cutover state, replays DHR row 46 into the successor, excludes only the exact invalid SLS partial, and projects no open positions. Reject any destructive or overbroad diff.

If a safe PR is produced, require the full exact-head safety suite before automatic squash merge, then validate authoritative Splendid deployment/bootstrap/daily-audit evidence. No user action is currently required.

## Completion Criteria for Issue #126

Issue #126 may close only after all are proven:
- prospective containment remains active;
- every v3 canonical row through the cutover boundary is independently classified;
- deterministic v3→v4 successor recovery completes from exact evidence;
- canonical ledger remains append-only/hash-valid and unchanged through recovery;
- active v4 accounting has zero unexplained coverage/economic issues;
- cash/equity/open positions match deterministic projection within bounded tolerances;
- authoritative Splendid bootstrap/runner/market-data/state diagnostics are healthy apart from any intentionally retained lifecycle halt;
- any halt release is separately justified by clean lifecycle evidence, never manual clearing;
- this handoff is refreshed with final clean state and Issue #126 closure.

## Working Principle

Correctness, accounting integrity, runtime stability, and deterministic recovery remain ahead of performance optimization. Resume performance work only after active stability/accounting issues are fully closed with clean authoritative evidence.
