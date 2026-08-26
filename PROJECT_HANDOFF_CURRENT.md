# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-08-26 16:42 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Runtime code baseline before this handoff refresh: `71c3e0777f82f3b1521b3ab17df53a25fb1d91d1` (squash merge of PR #127)  
Active recovery work: Issue #126, draft PR #128 `fix/issue-126-v3-v4-successor-recovery`

## Communication and Continuity

Keep Trading-bot progress updates in the currently active ChatGPT conversation until the user intentionally starts a new one. Before any intentional chat transition, refresh this handoff with the exact current repository/runtime boundary so the next conversation can continue without reconstructing history.

After every material finding, bug fix, PR, merge, authoritative runtime validation, blocker, accounting/risk boundary change, or issue closure, update this file. Do not leave the handoff stale behind the actual project state.

The user wants to be as hands-off as possible for bug/stability work. Do not ask the user to perform routine debugging, code edits, GitHub work, CI review, or runtime evidence collection when connected tools can do it. Notify the user when an issue is fixed and when a genuinely user-only action is required.

## Autonomous Bug-Fix Authorization

The user explicitly authorized automatic bug fixing for bounded correctness/stability defects.

For a demonstrated bug, the assistant may autonomously:
- investigate repository and authoritative Splendid evidence;
- create/update a bounded branch and PR;
- add focused regression coverage;
- repair CI failures that are directly caused by the proposed fix;
- require and review all mandatory exact-head safety gates;
- merge a routine safe bug-fix PR automatically once every required exact-head gate is green and the change remains inside the authority boundaries below;
- validate the authoritative Splendid deployment after merge;
- update this handoff and notify the user that the issue was fixed.

Do not wait for user permission for routine safe bug-fix merges that meet those conditions. Escalate to the user only when a decision crosses an authority boundary, requires credentials/UI action unavailable to connected tools, changes intended trading behavior, or cannot be resolved safely from evidence.

## Standing Safety / Authority Boundaries

- Paper-only unless the user separately authorizes live trading.
- Rules engine remains sole execution authority; ML/AI remains shadow-only.
- Never delete, edit, relabel, truncate, or fabricate immutable canonical execution-ledger rows.
- Never manually clear a lifecycle/risk halt merely to make an audit pass.
- Never manually rewrite `day_peak_equity`, risk-day history, account history, or historical accounting state merely to make an audit pass.
- Do not casually call `/paper/run`; prefer existing automated read-only runtime snapshots and audit evidence.
- Do not change strategy logic, signal/participation thresholds, sizing policy, hard-risk thresholds, live authority, or ML execution authority as part of bug/stability repair unless the user separately authorizes that behavior change.
- Historical corrections must be evidence-based successor accounting dispositions with archived evidence and validation hold, not edits to immutable history.
- Every relevant code fix must pass the exact-head Change Safety Audit, Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit, exact Gunicorn startup smoke, and any affected focused invariant suite before automatic merge.

## Scheduled Operational Audits

Active weekday audit cadence in `America/Chicago`:
- Morning audit: 09:30 CDT/CT.
- Midday audit: 12:00 CDT/CT.
- Pre-close audit: 14:30 CDT/CT, approximately 30 minutes before the regular U.S. equity close.

Each audit starts from this handoff, current GitHub state, open stability/accounting issues and PRs, and the authoritative Splendid paper runtime. It checks bootstrap/runner health, canonical ledger integrity, accounting coverage/economic integrity, cash/equity/positions sanity, recent executions, market-data accounting, and risk state. Demonstrated bugs should be fixed autonomously under the standing boundaries rather than merely reported.

An hourly condition watch for Issue #126 is also active while that repair remains open. It should notify only for meaningful progress, a fixed issue, a significant blocker, or a user-only action.

## Current Issue #126 Status

PR #127 was squash-merged into main as `71c3e0777f82f3b1521b3ab17df53a25fb1d91d1`. It prospectively fixed the re-entrant accounting repair that could resurrect an already-closed successor-epoch position during the narrow window between state mutation and canonical `record_trade()`.

Root cause: a valid SLS full exit mutated cash/deleted SLS, then `set_cooldown()` re-entered the legacy accounting wrapper before the new canonical exit row existed. The wrapper reconstructed the just-closed SLS position from the prior snapshot and restored it. That resurrected position later generated an impossible SLS partial execution.

PR #127 makes successor generations v3+ under validation hold observational/fail-closed for this accounting read and suppresses automatic state repair during that in-flight window. Verified-v2 legacy behavior is intentionally preserved.

Fresh settled post-merge Splendid evidence on the PR #127 code baseline proved:
- canonical ledger hash chain valid;
- ledger row count exactly 45;
- exactly three v3 canonical executions;
- no additional lifecycle artifact appeared after the prospective fix deployed;
- the only active accounting defect remains the exact known invalid SLS partial row;
- current contaminated v3 state remains safely halted and was not manually rewritten.

Exact v3 canonical rows relevant to the successor recovery:
1. Valid SLS full exit: execution `9ab93335faff4e3293d24ebe0bad4e87`, `4.353086829 @ 13.62`.
2. Valid DHR partial exit: execution `26702f252870490c8f1ddab86ce794f5`, `0.063287453 @ 217.61`.
3. Invalid re-entrant SLS partial: execution `90b22aad76074031906e0c6459dfa0bc`, `1.43651871 @ 13.005`, retained immutably but excluded from successor economics only if its full exact signature and chain position remain unchanged.

The deterministic clean projection from the verified v3 baseline plus the two valid v3 executions is approximately:
- cash `13460.434677`;
- equity around `13538.662872` using the retained DHR mark;
- sole open position DHR, quantity approximately `0.477461547`, entry `216.960007`;
- SLS closed.

The existing risk-controls object, lifecycle halt, current-day peak, and history must be preserved exactly through the accounting successor cutover. Halt release is a separate evidence boundary after clean-state validation.

## Draft PR #128 — v3 to v4 Successor Recovery

PR #128: `Recover Issue #126 into deterministic v4 successor epoch`  
Branch: `fix/issue-126-v3-v4-successor-recovery`  
Initial exact head at PR creation: `3eb2a513bd650dc318b5a351435a33a8e14d1153`  
Target successor epoch: `stable-paper-v4-20260826-successor01`

Design boundary:
- require exact verified v3 baseline and exact 45-row canonical shape;
- require exact signatures for the two valid v3 executions and the one invalid re-entrant SLS partial;
- archive complete v3 persistence before cutover;
- rebuild successor economics from the verified v3 baseline plus only the two valid v3 rows;
- retain all canonical rows unchanged and verify ledger bytes are identical before/after cutover;
- start v4 under validation hold;
- preserve risk controls/history exactly, including the lifecycle halt and current-day peak;
- provide exact marker-based startup retry handling if a legacy startup owner restores v3 after a completed bounded cutover;
- update legacy v1/v2/v3 compatibility readers only to recognize exact v4 lineage, without granting them v3→v4 write authority.

Initial PR #128 CI state at this handoff refresh:
- Stable Paper Core Stage-F focused invariant validation: PASS.
- Repository Safety and Performance Audit Validation: PASS.
- Architecture Debt Regression Gate: FAIL on structural debt growth only, not on accounting arithmetic. The gate reported +1 duplicate function group, +1 dynamic mutation target, +1 mutation overlap / overlapping mutation owner warning, and associated warning/info deltas.
- Change Safety and full Refactor/Startup audits were still running at the last check.

Do not merge PR #128 until the architecture-debt regression is repaired without weakening the gate and all mandatory exact-head checks are green. The current intended next action is to remove the demonstrated duplicate helper/mutation-overlap debt, rerun exact-head CI, then automatically merge if all safety gates pass and validate authoritative Splendid v4 evidence.

## Completion Criteria for Issue #126

Issue #126 may close only after all of the following are proven prospectively:
- PR #127 prospective containment remains active with no new resurrection/lifecycle artifact;
- deterministic v3→v4 successor recovery completes from exact evidence;
- canonical ledger remains append-only/hash-valid and byte-unchanged through recovery;
- active v4 accounting has zero unexplained coverage/economic issues;
- cash/equity/open positions match the deterministic projection within defined bounded tolerances;
- authoritative Splendid bootstrap/runner/market-data/risk diagnostics are healthy apart from any intentionally retained lifecycle halt;
- any halt release is separately justified by clean-state/lifecycle evidence rather than manual clearing;
- this handoff is refreshed with the final clean state and issue closure.

## Working Principle

Correctness, accounting integrity, runtime stability, and deterministic recovery remain ahead of performance optimization. Once the active stability/accounting issues are fully closed with clean authoritative evidence, performance work may resume under the separate strategy/risk-change authority process.