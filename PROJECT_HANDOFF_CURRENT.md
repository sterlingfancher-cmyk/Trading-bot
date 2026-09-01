# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-08-31 23:28 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Current `main` baseline before this handoff commit: `d7978b74a891aa630fb652549f997956cba401d8`  
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

Fresh forensic evidence showed the remaining v3→v4 verifier blocker was the persisted DHR alias shape, not a new economic or canonical-ledger defect. PR #141 made the DHR terminal-state verifier require the exact proven alias divergence: `qty` approximately the verified baseline DHR quantity and `shares` approximately the post-partial remainder, with both aliases required and no fallback.

PR #141 exact final head `0f92f4f216a60b1641d69a3516262af005a7205e` passed every required exact-head gate and was squash-merged as `39511bd53fe599a8e3a1564b7d3887af3021b29f`.

## 2026-08-31 Authoritative v4 Post-Deploy Evidence

The scheduled repository runtime-research audit on deployed `main` produced fresh authoritative Splendid evidence after PR #141:
- active epoch is `stable-paper-v4-20260826-successor01` under validation hold;
- canonical execution ledger remains hash-valid at exactly 46 rows with zero v4 rows;
- the exact four v3 rows remain immutable, including valid terminal DHR full exit `ae9d82d3d25748459f37842679d501cd`;
- invalid SLS partial `90b22aad76074031906e0c6459dfa0bc` remains retained immutably and excluded only from successor economics;
- deterministic successor replay is flat with no open positions, cash `13533.996429678442`, and equity approximately `13534.00`;
- lifecycle halt remains active with reason `canonical execution lifecycle integrity halt`;
- runner has no active error and market-data accounting passes.

This evidence proves the v3→v4 cutover itself completed as intended. It also exposed one remaining accounting-observability defect: the verified v4 baseline is intentionally flat (`positions={}`, `trades=[]`, cash approximately equity), but `verified_snapshot_accounting_baseline` forwarded that empty-trade shape into the legacy bidirectional reconciler, which reported `coverage_complete=false` solely because the trade ledger was empty. The same audit showed zero coverage issues and zero economic issues, so this was a reconciliation/reporting classification defect rather than a new canonical or economic defect.

## 2026-08-31 Flat Verified-Baseline Repair — PR #142

PR #142 adds a narrow fail-closed verified-flat baseline path. It reports accounting coverage complete only when the verified snapshot has:
- no baseline positions;
- no post-baseline trades;
- positive cash and equity;
- cash and equity within `$0.05`.

A flat snapshot with a material cash/equity mismatch remains a coverage failure. Existing verified-open-position behavior is unchanged. The repair does not mutate portfolio state, canonical history, risk state, halt/validation hold, strategy, signals, sizing, hard-risk thresholds, live authority, ML authority, or order authority.

PR #142 exact head `4db57469c2c75d36a5b3d0660bdffe521b908748` passed:
- Change Safety Audit, including impact-aware canonical invariant regressions and exact Gunicorn bootstrap startup smoke;
- Repository Safety and Performance Audit Validation;
- Architecture Debt Regression Gate;
- full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit.

PR #142 was squash-merged automatically as `baccd041751c8e2e4a603cec097bb16d4c21c73d`.

## 2026-08-31 PR #142 Deployment Boundary

Current `main` documentation baseline `d7978b74a891aa630fb652549f997956cba401d8` is deployed successfully to authoritative Splendid (`web-production-e1796.up.railway.app`). The exact-main Change Safety Audit also completed successfully. No new open repair PR or newly discovered correctness issue is present beyond Issue #126.

A fresh direct read-only request to the Splendid audit endpoint from the automation execution environment still fails at DNS resolution. Treat this as an evidence-access limitation only; do not infer active accounting health from deployment success alone and do not alter runtime state in response.

## Current Validation Boundary

Issue #126 remains open intentionally. Fresh read-only authoritative Splendid evidence after deployment of PR #142 must now prove:
- active epoch remains v4 under validation hold;
- canonical ledger remains append-only/hash-valid at the same immutable 46-row cutover boundary unless a legitimate new execution is independently explained;
- active accounting reports `coverage_complete=true` with zero coverage/economic issues;
- reconstructed cash/equity/open positions match the flat v4 successor baseline;
- lifecycle halt remains preserved unless a separate bounded release gate proves it safe to release;
- runner, market data, persistence, bootstrap, and accounting diagnostics remain healthy.

No `/paper/run`, manual halt/hold release, canonical mutation, day-peak rewrite, historical-state rewrite, or trading-authority change is authorized for this validation.

## Immediate Next Action

Obtain a fresh read-only authoritative Splendid repository runtime-research snapshot/audit from an execution path that can resolve the service. If active v4 accounting is clean and all other acceptance evidence remains intact, evaluate Issue #126 closure and any separate halt/validation-hold release boundary from that exact evidence only.

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
