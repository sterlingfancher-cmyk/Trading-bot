# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-09-02 12:05 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Validated runtime-code `main`: `cc5f6b6c2ed0b155a4a20b6ebd2210633b981e03` (PR #153).  
Active stability/accounting issue: none. Active runtime-observability/performance issue: none. Active repair PR: none.

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

## Established v4 Successor Boundary

Issue #126 was the post-#82 SLS canonical exit/state divergence caused by re-entrant legacy accounting during full-exit processing. PR #127 prospectively contained the resurrection defect. PR #128 and subsequent bounded verifier repairs established deterministic v3→v4 successor recovery without rewriting immutable history.

The exact recovery disposition remains:
- retain all canonical rows immutably;
- include the valid SLS full exit;
- include the valid DHR partial exit;
- include the valid canonical-only terminal DHR full exit;
- exclude only the proven invalid re-entrant SLS partial from successor economics;
- preserve validation hold, risk/day-peak history, strategy, sizing, hard-risk limits, live authority, and ML authority.

The authoritative active epoch is `stable-paper-v4-20260826-successor01`. Issue #126 is closed. Validation hold remains intentionally active and must only be released through a separate governed validation-release gate.

## Recently Closed Runtime/Observability Issues

### Issue #143 — legacy v2 diagnostic false WARN

PR #145 made the legacy verified-v2 recovery gate non-applicable when an active v4+ lineage is proven while retaining the raw forensic evidence. It also made optional root-route failures nonblocking only when required core runtime health is independently proven. Issue #143 is closed.

### Issue #146 — `/paper/status` and root latency

PRs #147–#149 progressively removed expensive read-only status persistence/reconciliation, added lightweight in-memory core status views, and fixed root JSON content negotiation. Final settled Splendid acceptance proved `/paper/status` and root respond normally while preserving all trading/state authority boundaries. Issue #146 is closed.

## 2026-09-02 Issue #150 — DELL Serialized Micro-Share Residue — CLOSED

### Morning finding

The morning audit found a read-only accounting classification defect, not a canonical or persisted-state defect. Authoritative Splendid was flat with cash approximately `13475.004711`, equity approximately `13475.00`, and no persisted positions, while deterministic accounting reconstruction incorrectly reported DELL as open.

The DELL v4 lifecycle was:
- short entry `2.323047 @ 436.96`;
- partial exit `0.766605 @ 426.25`;
- terminal exit `1.556441 @ 466.10`.

Six-decimal serialization leaves exactly `0.000001` share arithmetic residue. `paper_bidirectional_accounting_guard.py` already defined `STATE_TRADE_QTY_SERIALIZATION_TOLERANCE = 5e-6`, but the final reconstructed-open-position predicate still used `> 1e-9`.

Two unsafe repo-agent attempts, PRs #151 and #152, were rejected and closed unmerged because they destructively rewrote unrelated production code. No unsafe change reached `main`.

### PR #153 repair

PR #153 applied the bounded intended repair: use the existing `5e-6` serialization tolerance only for final reconstructed-open-position classification, preserving exit-overrun tolerance, cash/economic arithmetic, canonical semantics, persistence/state, strategy, signals, sizing, risk thresholds, halt/validation hold, live authority, ML authority, and order authority. Focused regressions cover the DELL `1e-6` terminal residue, a residue above `5e-6`, and existing over-exit behavior.

PR #153 exact head `7a3933831a4c56bba6eb78a976f1a1f0b006c2b0` passed every required exact-head gate:
- Change Safety Audit;
- Repository Safety and Performance Audit Validation;
- Architecture Debt Regression Gate;
- full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit;
- exact Gunicorn startup smoke;
- focused accounting regressions.

It was squash-merged as runtime commit `cc5f6b6c2ed0b155a4a20b6ebd2210633b981e03`.

The first automatic post-merge runtime artifact was captured while Splendid was still in deferred registration and was deliberately rejected as acceptance evidence. Issue #150 was reopened until a settled read-only capture could prove the runtime result.

### 2026-09-02 12:03 CDT settled Splendid acceptance

A fresh rerun against the fully settled authoritative deployment proved:
- bootstrap ready, phase `delegating`, application ready;
- all `11/11` runtime-research endpoints reachable; no required endpoint or classification failures;
- self-check `pass`, no failing components;
- active epoch `stable-paper-v4-20260826-successor01` with `validation_hold=true`;
- persisted cash `13475.004711441643`, equity `13475.0`, positions `[]`;
- accounting model `bidirectional_margin_v1`, coverage complete, `coverage_issue_count=0`, `economic_issue_count=0`;
- reconstructed cash/equity `13475.004291` / `13475.004291`;
- critically, `reconstructed_open_positions=[]`: the DELL phantom lot is gone;
- canonical execution ledger append-only/hash-valid at 55 rows, 9 current-v4 rows, zero parse/hash errors; latest execution ID `300a83cb7ec14b69884f701ca847ec01`;
- market-data accounting `pass`, `7782/7782` requests classified, zero in-flight/unclassified requests, provider circuit closed;
- runner `pass`, no active error, last successful automatic run approximately `12:03:15 CDT`, last completed cycle approximately `12:03:19 CDT`;
- fresh risk day `pass`; risk not halted; intraday drawdown approximately `2.43%`; net daily loss approximately `0.568%`; self-defense inactive with reason `feedback loop clear`;
- the snapshot-level `WARN` is solely the explicitly non-applicable legacy verified-v2 gate (`superseded_by_active_v4_plus_lineage`), not an active v4 defect.

Issue #150 is closed as completed on this settled evidence. No canonical/state/history/risk/strategy/sizing/live/ML/order authority was changed.

## Current Validation Boundary

There is currently no demonstrated canonical/accounting correctness defect, no active runtime endpoint-latency defect, no runner error, no market-data accounting gap, and no risk halt. The active v4 successor remains under validation hold by design.

Do not release validation hold merely because Issues #126, #143, #146, and #150 are closed. Require a bounded governed release gate proving configured forward-validation criteria while preserving canonical history, risk/day-peak history, strategy, sizing, hard-risk thresholds, live authority, and ML authority.

No `/paper/run`, manual halt/hold release, canonical mutation, day-peak rewrite, historical-state rewrite, or trading-authority change is authorized by this handoff.

## Immediate Next Action

Continue the scheduled morning, midday, and pre-close read-only operational audits against Splendid. If a new demonstrated bug appears, repair it automatically within the standing safety boundary, require all exact-head gates, merge only when green, validate authoritative Splendid deployment evidence, and record every material finding/repair/merge/runtime result in this handoff.

Separately evaluate validation-hold release only from explicit clean forward-validation evidence; do not manually clear the hold.

Correctness, accounting integrity, runtime stability, and deterministic recovery remain ahead of performance optimization.
