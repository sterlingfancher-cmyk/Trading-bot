# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-09-01 09:35 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Current `main` baseline before this handoff commit: `d0eeb3f426df23c7c9305ed09e4f1c3132ec9cac`  
Active stability/accounting issue: none; Issue #126 closed completed on 2026-09-01

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

Issue #126 was the post-#82 SLS canonical exit/state divergence. The prospective defect was a re-entrant legacy accounting read during SLS full-exit processing: state deleted SLS, then cooldown/accounting re-entry occurred before the new canonical row had been mirrored into state, allowing the closed position to be reconstructed and later emit an impossible SLS partial exit.

PR #127 prospectively contained that re-entrant resurrection defect. PR #128 added deterministic v3→v4 successor recovery with immutable canonical history, exact-signature evidence, archival, validation hold, and preserved lifecycle halt. Subsequent evidence expanded the exact v3 cutover boundary to 46 canonical rows, including a valid canonical-only terminal DHR full exit whose state/cash mirror did not complete.

The recovery disposition remains exact:
- retain all canonical rows immutably;
- include the valid SLS full exit;
- include the valid DHR partial exit;
- include the valid canonical-only terminal DHR full exit;
- exclude only the proven invalid re-entrant SLS partial from successor economics;
- preserve validation hold, risk history, day peak, strategy, sizing, hard-risk limits, live authority, and ML authority;
- require clean authoritative v4 post-deploy evidence before Issue #126 closure.

## 2026-08-31 DHR Alias-Shape Repair — PR #141

Fresh forensic evidence showed the remaining v3→v4 verifier blocker was the persisted DHR alias shape, not a new economic or canonical-ledger defect. PR #141 made the DHR terminal-state verifier require the exact proven alias divergence: `qty` approximately the verified baseline DHR quantity and `shares` approximately the post-partial remainder, with both aliases required and no fallback.

PR #141 exact final head `0f92f4f216a60b1641d69a3516262af005a7205e` passed every required exact-head gate and was squash-merged as `39511bd53fe599a8e3a1564b7d3887af3021b29f`.

## 2026-08-31 Authoritative v4 Post-Deploy Evidence

The scheduled repository runtime-research audit on deployed `main` produced fresh authoritative Splendid evidence after PR #141:
- active epoch is `stable-paper-v4-20260826-successor01` under validation hold;
- canonical execution ledger remained hash-valid at exactly 46 rows with zero v4 rows at that time;
- the exact four v3 rows remained immutable, including valid terminal DHR full exit `ae9d82d3d25748459f37842679d501cd`;
- invalid SLS partial `90b22aad76074031906e0c6459dfa0bc` remained retained immutably and excluded only from successor economics;
- deterministic successor replay was flat with no open positions, cash `13533.996429678442`, and equity approximately `13534.00`;
- lifecycle halt remained active with reason `canonical execution lifecycle integrity halt`;
- runner had no active error and market-data accounting passed.

This evidence proved the v3→v4 cutover itself completed as intended. It also exposed one remaining accounting-observability defect: the verified v4 baseline was intentionally flat (`positions={}`, `trades=[]`, cash approximately equity), but `verified_snapshot_accounting_baseline` forwarded that empty-trade shape into the legacy bidirectional reconciler, which reported `coverage_complete=false` solely because the trade ledger was empty. The same audit showed zero coverage issues and zero economic issues, so this was a reconciliation/reporting classification defect rather than a new canonical or economic defect.

## 2026-08-31 Flat Verified-Baseline Repair — PR #142

PR #142 added a narrow fail-closed verified-flat baseline path. It reports accounting coverage complete only when the verified snapshot has:
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

## 2026-09-01 Morning Acceptance — Issue #126 Closed

A fresh read-only authoritative Splendid runtime-research capture completed at approximately 09:32 CDT using the deployed PR #142 code. The runtime and accounting acceptance boundary is now clean:
- active epoch remains `stable-paper-v4-20260826-successor01` under validation hold;
- daily audit reports `overall=pass` and accounting integrity `status=ok`;
- `coverage_complete=true`, `coverage_issue_count=0`, and `economic_issue_count=0`;
- canonical execution ledger is append-only/hash-valid at 48 rows with 2 current-v4 rows;
- the two new post-cutover rows form a legitimate exact NVDA short lifecycle: entry `9c0aaec4bf2547bc9fff1f4514687025`, 4.698849 @ 216.021, followed by exit `666fe83500a540cebce5bb142553f5f1`, 4.698849 @ 218.31;
- active state is flat with no open positions; cash is `13523.240757873831`, equity `13523.24`, and reconstructed cash/equity `13523.240764`;
- runner is PASS with no active error and last successful run `2026-09-01 09:29:24 CDT`;
- market-data accounting is PASS with 7,593 classified terminal outcomes and zero in-flight/unclassified requests;
- fresh-day baseline is sane/pass with `day_start_equity=13533.996429678442`, `day_peak_equity=13534.0`, and approximately 0.079% daily loss/drawdown;
- risk is PASS and no lifecycle/risk halt is currently active;
- self-check is PASS with no failing components;
- the v3→v4 migration provenance remains archived and exact, and the invalid SLS partial remains immutable historical evidence excluded only from successor economics.

The runtime-research wrapper reports `warn` only because it still invokes the superseded verified-v2 successor replay probe. That probe correctly rejects the active v4 lineage with diagnosis `canonical_ledger_epoch_lineage_not_exactly_verified_v2`; it is not an active v4 accounting failure and has no write, halt-clear, risk-peak, strategy, sizing, live, or ML authority.

Issue #126 was closed as completed on this evidence. No code repair or state mutation was required during the 2026-09-01 morning audit. Validation hold remains active and should only be released through a separate governed validation-release decision; Issue #126 closure does not itself authorize hold release.

## Current Validation Boundary

There is no active stability/accounting defect. Continue routine read-only morning, midday, and pre-close operational audits. Treat any future canonical/accounting/runtime regression as a new issue unless evidence proves it is a continuation of an existing defect.

The next governed decision is validation-hold release for the clean v4 successor. Do not release it merely because Issue #126 is closed. Require a bounded release gate proving the configured forward-validation criteria are satisfied while preserving canonical history, risk/day-peak history, strategy, sizing, hard-risk thresholds, live authority, and ML authority.

No `/paper/run`, manual halt/hold release, canonical mutation, day-peak rewrite, historical-state rewrite, or trading-authority change is authorized by this handoff.

## Immediate Next Action

Continue normal autonomous audits against authoritative Splendid. If v4 accounting, canonical lifecycle, runner, market-data, persistence, fresh-day risk state, or startup health regresses, investigate and repair it under the standing bounded safety rules. Separately evaluate the existing validation-hold release mechanism only from explicit clean forward-validation evidence; do not manually clear the hold.

Correctness, accounting integrity, runtime stability, and deterministic recovery remain ahead of performance optimization.
