# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-08-31 20:38 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Current `main` before this handoff commit: `2d3e120c9dd389d71097fb4479279b69217ae610`  
Current Issue #126 repair baseline: `39511bd53fe599a8e3a1564b7d3887af3021b29f` (squash merge of PR #141)  
Active stability/accounting issue: Issue #126

## Communication and Continuity

Keep all Trading-bot progress, blockers, merge notices, runtime findings, and issue-status updates in the currently active main ChatGPT Trading conversation. Do not branch individual issue updates into separate chats unless the user explicitly requests a transition.

Routine bounded stability work should be handled automatically: investigate, repair, test, merge when every required exact-head gate is green, then validate authoritative Splendid deployment evidence. Escalate only genuinely blocked or authority-changing decisions.

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

PR #141 changed only the production verifier boundary so `canonical_only_terminal_dhr_state_shape_exact` requires all of the following fail-closed:
- positions exactly `DHR` and `SLS`;
- DHR side `long`;
- DHR `qty` approximately `EXPECTED_BASELINE_DHR_QTY`;
- DHR `shares` approximately `EXPECTED_DHR_REMAINDER`;
- both aliases must be present and valid; there is no fallback.

Focused regressions cover the valid production alias divergence, wrong qty, wrong shares, missing qty, missing shares, and both aliases incorrectly set to the remainder. Two older Issue #126 test fixtures that still encoded the superseded `qty == remainder` shape were corrected to baseline `qty` plus remainder `shares` without weakening production checks.

PR #141 exact final head `0f92f4f216a60b1641d69a3516262af005a7205e` passed every required exact-head gate, including Change Safety Audit, Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit, impact-aware canonical invariant regressions, and exact Gunicorn bootstrap startup smoke.

PR #141 was squash-merged automatically as `39511bd53fe599a8e3a1564b7d3887af3021b29f`.

## 2026-08-31 Post-Merge Deployment Status

The subsequent handoff commit `2d3e120c9dd389d71097fb4479279b69217ae610` is green on current `main`.

GitHub commit status now confirms successful Railway deployment to the authoritative Splendid service `web-production-e1796.up.railway.app`. The legacy Railway deployment is also green, and the exact-head Change Safety Audit on current `main` is successful.

There are no open repair pull requests. No new operational issue has been demonstrated beyond the still-open Issue #126 acceptance boundary.

Direct read-only Splendid access from the current automation execution environment still fails intermittent DNS resolution. This is an observation-environment limitation only and is not production-failure evidence. Because the decisive v4 accounting/runtime payload could not be fetched from this environment in this run, do not infer that Issue #126 is complete solely from deployment success.

## Current Validation Boundary

No canonical row, lifecycle halt, validation hold, day peak, historical accounting state, strategy, signals, sizing, hard-risk threshold, live authority, ML authority, or order authority was manually changed by the PR #141 repair or handoff updates.

Authoritative post-deploy Splendid validation is still required before Issue #126 may close. Fresh read-only runtime evidence must prove:
- deployed runtime contains the PR #141 repair;
- v4 successor cutover completes or is already active as intended;
- canonical ledger remains append-only/hash-valid and unchanged through recovery;
- active v4 accounting has zero unexplained coverage/economic issues;
- cash/equity/open positions match the deterministic successor projection;
- validation hold remains active;
- lifecycle halt remains active unless independently proven safe to release through a separate bounded evidence gate;
- bootstrap, runner, market data, state persistence, and accounting diagnostics are healthy.

## Immediate Next Action

Obtain the next fresh read-only authoritative Splendid runtime snapshot/audit, preferably through an existing repository automation artifact when direct network access is unavailable. Do not call `/paper/run`, manually release the halt/validation hold, or close Issue #126 before the post-deploy acceptance boundary is proven.

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
