# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-08-31 17:41 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Current `main` repair baseline before this handoff commit: `39511bd53fe599a8e3a1564b7d3887af3021b29f` (squash merge of PR #141)  
Active stability/accounting issue: Issue #126

## Communication and Continuity

Keep all Trading-bot progress, blockers, merge notices, runtime findings, and issue-status updates in the currently active main ChatGPT Trading conversation. Do not branch individual issue updates into separate chats unless the user explicitly requests a transition.

The user wants routine bounded stability work handled automatically: investigate, repair, test, merge when every required exact-head gate is green, then validate authoritative Splendid deployment evidence. Escalate only genuinely blocked or authority-changing decisions.

## Standing Safety / Authority Boundaries

- Paper-only unless separately authorized.
- Rules engine remains sole execution authority; ML/AI remains shadow-only.
- Never delete, edit, relabel, truncate, fabricate, or reorder immutable canonical execution-ledger rows.
- Never manually clear lifecycle/risk halts or validation holds merely to make an audit pass.
- Never rewrite day peaks, risk-day history, account history, or historical accounting state merely to make an audit pass.
- Do not casually call `/paper/run`; prefer automated read-only runtime snapshots/audits.
- Do not change strategy logic, signal/participation thresholds, sizing policy, hard-risk thresholds, live authority, or ML execution authority as part of stability repair without separate authorization.
- Historical accounting correction must use exact-evidence successor accounting with archived evidence and validation hold, never immutable-history edits.
- Relevant repairs require exact-head Change Safety Audit, Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit, exact Gunicorn startup smoke, and affected focused invariant suites before automatic merge.

## Issue #126 — Established Root Cause and Recovery Boundary

Issue #126 is the post-#82 SLS canonical exit/state divergence. The prospective defect was a re-entrant legacy accounting read during SLS full-exit processing: state deleted SLS, then cooldown/accounting re-entry occurred before the new canonical row had been mirrored into state, allowing the closed position to be reconstructed and later emit an impossible SLS partial exit.

PR #127 prospectively contained that re-entrant resurrection defect. PR #128 added deterministic v3→v4 successor recovery with immutable canonical history, exact-signature evidence, archival, validation hold, and preserved lifecycle halt. Subsequent evidence expanded the exact v3 cutover boundary to 46 canonical rows, including a valid canonical-only terminal DHR full exit whose state/cash mirror did not complete.

The recovery disposition remains exact:
- retain all canonical rows immutably;
- include the valid SLS full exit;
- include the valid DHR partial exit;
- include the valid canonical-only terminal DHR full exit;
- exclude only the proven invalid re-entrant SLS partial from successor economics;
- preserve current halt, validation hold, risk history, day peak, strategy, sizing, hard-risk limits, live authority, and ML authority;
- require clean authoritative v4 post-deploy evidence before any hold/halt release or Issue #126 closure.

## 2026-08-31 DHR Alias-Shape Repair — PR #141

Fresh forensic evidence showed the remaining v3→v4 verifier blocker was the persisted DHR alias shape, not a new economic or canonical-ledger defect. The authoritative pre-cutover state uses two deliberately different aliases:
- DHR `qty` remains approximately the verified baseline DHR quantity;
- DHR `shares` is approximately the post-partial DHR remainder.

The previous migration predicate used a permissive `qty` with `shares` fallback and compared the selected value to the remainder. That could not represent the proven persisted alias divergence exactly.

PR #141 changed only the production verifier boundary so `canonical_only_terminal_dhr_state_shape_exact` now requires all of the following fail-closed:
- positions exactly `DHR` and `SLS`;
- DHR side `long`;
- DHR `qty` approximately `EXPECTED_BASELINE_DHR_QTY`;
- DHR `shares` approximately `EXPECTED_DHR_REMAINDER`;
- both aliases must be present and valid; there is no fallback.

Focused regressions were added for the valid production alias divergence, wrong qty, wrong shares, missing qty, missing shares, and both aliases incorrectly set to the remainder. Two older Issue #126 test fixtures still encoded the superseded `qty == remainder` shape; they were corrected to model baseline `qty` plus remainder `shares` without weakening any production check or safety expectation.

PR #141 exact final head `0f92f4f216a60b1641d69a3516262af005a7205e` passed every required exact-head gate:
- Change Safety Audit;
- Repository Safety and Performance Audit Validation;
- Architecture Debt Regression Gate;
- full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit;
- impact-aware canonical invariant regressions;
- exact Gunicorn bootstrap startup smoke.

PR #141 was squash-merged automatically as `39511bd53fe599a8e3a1564b7d3887af3021b29f` after all required gates were green.

## Current Validation Boundary

No canonical row, lifecycle halt, validation hold, day peak, historical accounting state, strategy, signals, sizing, hard-risk threshold, live authority, ML authority, or order authority was manually changed by the PR #141 repair.

Authoritative post-merge Splendid validation is still required before Issue #126 may close. The next fresh runtime evidence must prove:
- deployment contains the PR #141 merge;
- v4 successor cutover completes or is already active as intended;
- canonical ledger remains append-only/hash-valid and unchanged through recovery;
- active v4 accounting has zero unexplained coverage/economic issues;
- cash/equity/open positions match the deterministic successor projection;
- validation hold remains active;
- lifecycle halt remains active unless independently proven safe to release through a separate bounded evidence gate;
- bootstrap, runner, market data, state persistence, and accounting diagnostics are healthy.

Direct Splendid network access from the current automation execution environment has intermittently failed DNS resolution. Treat that as an observation-environment limitation only; it is not evidence of a production-runtime failure. Prefer the repository's automated authoritative Splendid snapshot/audit artifacts when direct access is unavailable.

## Immediate Next Action

Wait for the PR #141 merge deployment to reach Splendid, then obtain fresh read-only authoritative runtime evidence. Do not call `/paper/run`, manually release the halt/validation hold, or close Issue #126 before the post-deploy acceptance boundary is proven.

If a new regression is demonstrated, create the narrowest paper-only repair, preserve immutable evidence and authority boundaries, add focused regressions, and require the complete exact-head safety gate set before merge.

## Completion Criteria for Issue #126

Issue #126 may close only after all are proven:
- prospective containment remains active;
- every v3 canonical row through the cutover boundary remains independently classified;
- deterministic v3→v4 successor recovery completes from exact evidence;
- canonical ledger remains append-only/hash-valid and unchanged through recovery;
- active v4 accounting has zero unexplained coverage/economic issues;
- cash/equity/open positions match deterministic projection within bounded tolerances;
- authoritative Splendid bootstrap/runner/market-data/state diagnostics are healthy apart from any intentionally retained lifecycle halt;
- any halt or validation-hold release is separately justified by clean lifecycle evidence, never manual clearing.

Correctness, accounting integrity, runtime stability, and deterministic recovery remain ahead of performance optimization.
