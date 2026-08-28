# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-08-28 09:46 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Current runtime code baseline: `54df8c9edf43af645b5abac4f6d93c262aeeff37` (squash merge of PR #134)  
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

Known v3 rows from the original 45-row proof boundary:
1. Valid SLS full exit `9ab93335faff4e3293d24ebe0bad4e87`.
2. Valid DHR partial exit `26702f252870490c8f1ddab86ce794f5`.
3. Proven invalid re-entrant SLS partial `90b22aad76074031906e0c6459dfa0bc`, retained immutably but excluded from successor economics only when its exact signature remains proven.

## 2026-08-28 Morning Repair — PR #134

The remaining verifier defect was numeric price comparison against canonical ledger values serialized with `round(price, 6)`. Repo-agent attempts #129-#133 were rejected/closed unmerged because their generated file replacement diffs were destructive. No unsafe replacement was merged.

A direct bounded repair was created on `fix/issue126-price-serialization-20260828`:
- production diff exactly one line: `PRICE_TOLERANCE = 1e-9` -> `PRICE_TOLERANCE = 5e-6` in `verified_v3_successor_epoch_migration.py`;
- added `tests/test_verified_v3_signature_checks.py` proving an in-bound serialization delta passes only with exact identity/event hash, an out-of-bound price fails, and event-hash mismatch remains fail-closed.

PR #134 exact head `c3cef758d1e2a0fdcd414168402c3cbd6b5fd585` passed every required exact-head gate, including Change Safety impact-aware regressions/core invariant suite, Repository Safety/Performance, Architecture Debt, full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research audit, focused Stable Paper regressions, and both exact Gunicorn startup smokes. It was squash-merged automatically as current runtime code baseline `54df8c9edf43af645b5abac4f6d93c262aeeff37`.

Both Railway deployment contexts and the post-merge repository/refactor validations are green.

Fresh Splendid bootstrap evidence after deployment proves the price repair worked: all three previously known v3 rows now pass every exact check — ledger index, execution ID, accounting epoch, action, symbol, side, quantity, price, and immutable event hash.

## New Fail-Closed Boundary — Canonical Row 46

Fresh authoritative Splendid evidence at approximately 09:41-09:43 CDT shows the canonical ledger legitimately advanced while Issue #126 was being repaired:
- canonical chain: valid and parse-clean;
- total canonical rows: 46;
- active v3 canonical rows: 4;
- last execution ID: `ae9d82d3d25748459f37842679d501cd`;
- the migration still expects the previously proven 45-row / 3-v3-row evidence boundary.

Therefore v3→v4 migration correctly remains blocked. This is no longer the old price-tolerance defect. Do **not** increase `EXPECTED_LEDGER_ROW_COUNT`, accept the fourth row, exclude it, or replay it until the exact immutable row metadata and economic effect of execution `ae9d82d3d25748459f37842679d501cd` are independently proven. The row may be a legitimate exit under the fail-closed risk halt; classification must come from evidence, not inference.

Current migration status:
- baseline exact: PASS;
- all three original known row signatures: PASS;
- canonical chain: PASS;
- existing lifecycle halt preserved: PASS;
- exact-three-v3-row boundary: FAIL because v3 row count is now 4;
- deterministic projection/cross-check: intentionally not run because canonical precondition failed.

## Current Authoritative Splendid Runtime — 2026-08-28 Morning

Fresh read-only runtime snapshot and full daily-audit evidence:
- application bootstrap: ready/delegating after normal cold-start registration; delegate ready;
- runner: PASS, no active error; latest successful run `2026-08-28 09:34:57 CDT`; latest completed cycle `09:35:06 CDT`;
- canonical ledger: PASS, append-only/hash-valid, 46 rows, 4 current-v3 rows;
- account cash: approximately `13483.476479`;
- account equity: approximately `13602.08`;
- active state positions: `DHR`, `SLS`;
- active state trade rows: 3;
- accounting integrity: WARN because the exact known invalid SLS partial remains unmatched; coverage issue count 1, economic issue count 1 in the compact audit;
- reconstructed clean state from the three state-trade rows remains DHR-only, but no successor write is allowed until row 46 is classified;
- market data: PASS; provider circuit clear; no provider failures in the audited snapshot;
- state persistence: PASS; persistent mount, state and backup present, in-memory/on-disk richness matched;
- fresh-day baseline: sane; date `2026-08-28`, day start/peak approximately `13606.02`, reset not pending;
- risk: intentionally FAIL because `canonical execution lifecycle integrity halt` remains active; intraday drawdown approximately `0.029%`;
- validation hold remains active;
- no strategy/sizing/risk-threshold/live/ML authority was changed.

The overall daily audit remains FAIL because of the intentional lifecycle/accounting safety boundary, not because runner, state persistence, market data, canonical hash chain, or fresh-day initialization are unhealthy.

## Immediate Next Action

Obtain read-only exact forensic evidence for canonical execution `ae9d82d3d25748459f37842679d501cd`: ledger index, epoch, action, symbol, side, quantity, price, event hash, predecessor hash/order, matching state/journal evidence, and economic effect. Determine whether it is a valid post-containment execution or a new lifecycle artifact.

Only after that evidence is complete may the successor migration evidence boundary be revised. Any revision must remain exact-signature based, preserve every canonical row immutably, keep validation hold/lifecycle halt fail-closed, and pass the full mandatory gate suite before merge. No user action is currently required.

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