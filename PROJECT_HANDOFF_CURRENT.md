# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-09-01 14:39 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Current `main`: `7d821b6ebb1cd517a8b857fd52d3f8e6e63ae9f6`  
Active stability/accounting issue: none; active runtime-observability/performance issue: Issue #146; active repair PR: #148

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

PR #142 exact head `4db57469c2c75d36a5b3d0660bdffe521b908748` passed Change Safety Audit, Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, the full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit, and exact Gunicorn startup smoke. PR #142 was squash-merged automatically as `baccd041751c8e2e4a603cec097bb16d4c21c73d`.

## 2026-09-01 Morning Acceptance — Issue #126 Closed

A fresh read-only authoritative Splendid runtime-research capture completed at approximately 09:32 CDT using the deployed PR #142 code. The runtime and accounting acceptance boundary was clean:
- active epoch remained `stable-paper-v4-20260826-successor01` under validation hold;
- daily audit reported `overall=pass`, accounting coverage complete, zero coverage issues, and zero economic issues;
- canonical execution ledger remained append-only/hash-valid;
- runner, market-data accounting, fresh-day state, risk, and self-check passed;
- the v3→v4 migration provenance remained archived and exact, with the invalid SLS partial retained as immutable historical evidence and excluded only from successor economics.

Issue #126 was closed as completed on this evidence. Validation hold remains active and should only be released through a separate governed validation-release decision; Issue #126 closure does not itself authorize hold release.

## 2026-09-01 Issue #143 Resolution — PR #145

Issue #143 tracked a diagnostics-only false WARN in `runtime_research_snapshot.py`: the collector treated the legacy verified-v2 recovery gate as active on a healthy v4 lineage and treated the optional root endpoint as blocking even when required runtime health was proven.

PR #145 implemented a surgical two-file repair:
- preserve collection/raw evidence from the legacy verified-v2 recovery endpoint;
- when active daily-audit epoch is `stable-paper-v4-*` or later, mark that old v2 gate superseded/non-applicable to overall classification;
- preserve fail-closed behavior for active verified-v2 failures;
- permit root `/` to be nonblocking only when bootstrap, paper status, application readiness, and self-check prove required health;
- preserve warning behavior for required endpoint, self-check, fresh-day, daily-audit, accounting/risk, and research-run failures;
- add focused regressions for v4 lineage, optional root failure, and required endpoint failures.

Exact PR head `e3204ea6f3174ea2d31f0624fa110d963bb9369c` passed Change Safety Audit including impact-aware canonical invariant regressions and exact Gunicorn smoke, Repository Safety/Performance, Architecture Debt, and the full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research audit. PR #145 was squash-merged as `3421829a68d898bbb413e5638372c95f78fb1177` and authoritative Splendid deployment succeeded.

A fresh post-deploy retry confirmed the intended Issue #143 behavior: active `stable-paper-v4-20260826-successor01` makes the legacy verified-v2 gate nonblocking while retaining its raw evidence. Issue #143 is therefore closed as completed.

## Issue #146 — Required Core Status/Root Latency

The post-PR-145 authoritative retry exposed a distinct runtime-observability/performance defect. `/paper/status` is explicitly a required core endpoint in the self-check contract, yet both `/paper/status` and `/` exceeded the runtime research collector's 20-second read timeout on two attempts.

PR #147 (`fix/issue-146-readonly-status-persistence`) removed the redundant persistence/stale-write reconciliation triggered by GET/HEAD `/paper/status`. Exact head `0e8546cf4947326566050f67344eb88a31f81962` passed all required exact-head gates and was squash-merged as `593437000b5a5ce015ae0668d468df626d7fc203`.

### 2026-09-01 14:30 CDT Fresh Acceptance Retry — PR #147 Insufficient

The first main-push runtime snapshot after PR #147 landed was captured while Splendid was still in deferred bootstrap and therefore was not valid acceptance evidence. A fresh read-only rerun after the application had fully settled established the actual state:
- bootstrap was ready/delegating and application readiness was true;
- `/paper/self-check`, `/paper/fresh-day-check`, `/paper/daily-audit`, and the research/status endpoints other than the two core views were responsive;
- `/paper/status` still timed out after two 20-second attempts;
- root `/` also still timed out after two 20-second attempts;
- active epoch remained `stable-paper-v4-20260826-successor01` with `validation_hold=true`;
- accounting coverage remained complete with `coverage_issue_count=0` and `economic_issue_count=0`;
- canonical execution ledger remained append-only/hash-valid at 53 rows, with 7 active-v4 rows;
- open positions were BBAI and DELL; cash was approximately `11835.98`; equity approximately `13548.40`;
- runner was enabled with no active error and last successful automatic cycle at approximately 14:24:51 CDT;
- market-data accounting passed and the provider circuit remained closed;
- fresh-day baseline passed, risk was not halted, and intraday drawdown was approximately `0.011%`;
- self-defense was active only because the runtime was inside the configured final 30 minutes before the regular close. The compact daily audit therefore reported FAIL from that intentional late-day entry-defense condition, not from account loss, canonical divergence, lifecycle corruption, runner failure, or a new accounting defect.

This proves PR #147 removed one expensive save path but did not remove the remaining latency source. Static trace shows the legacy root and `/paper/status` handlers still execute status-building work that can touch equity/risk/market/scanner/state-diagnostic surfaces during a read-only request.

### PR #148 — Lightweight Read-Only Core Status Views

Active PR #148 (`fix/issue-146-lightweight-core-status`) is the bounded successor repair. It replaces only Flask view ownership for `home` and `paper_status` with a small in-memory snapshot overlay registered last in the existing runtime overlay stack. The new views read already-materialized portfolio/runtime fields only. They do not call `save_state`, state/journal reconciliation, `calculate_equity`, market-data fetches, scanner work, state-file diagnostics, automatic/manual cycles, order methods, or authority-changing code. Focused regressions explicitly fail if the new views invoke those legacy helpers and verify that endpoint ownership can be reasserted deterministically.

Current PR #148 head before this handoff update: `b52a1e07e7b0d6224b2c7667ce0a5909baedadca`. The pre-PR compare is bounded to one new read-only overlay, one focused test module, and a small `usercustomize.py` registration change; no `app.py` trading logic, persistence implementation, accounting/recovery code, risk logic, strategy/signals/sizing, canonical ledger, live authority, or ML authority is changed.

Do not merge PR #148 unless the exact final head passes Change Safety Audit, Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit including exact Gunicorn smoke, and the focused Issue #146 regressions. After merge/deployment, require a fresh authoritative Splendid read-only snapshot proving both `/paper/status` and root respond inside the normal 20-second collector boundary before closing Issue #146.

## Current Validation Boundary

There is no active canonical/accounting correctness defect. Issue #146 is an observability/performance defect isolated to the legacy required core status/root views. The late-day self-defense condition observed at 14:30 CDT is expected policy behavior and does not authorize any risk/halt/hold change.

The next governed trading-state decision remains validation-hold release for the clean v4 successor. Do not release it merely because Issue #126 is closed. Require a bounded release gate proving the configured forward-validation criteria are satisfied while preserving canonical history, risk/day-peak history, strategy, sizing, hard-risk thresholds, live authority, and ML authority.

No `/paper/run`, manual halt/hold release, canonical mutation, day-peak rewrite, historical-state rewrite, or trading-authority change is authorized by this handoff.

## Immediate Next Action

Validate PR #148 at its exact final head. If every required gate and focused regression is green and the diff remains bounded, squash-merge automatically. Then wait for authoritative Splendid deployment to settle and run a fresh read-only runtime snapshot. Close Issue #146 only when `/paper/status` and `/` are responsive inside the normal collector timeout and there is no new genuine required endpoint/runtime/accounting/canonical/risk failure.

Separately evaluate validation-hold release only from explicit clean forward-validation evidence; do not manually clear the hold.

Correctness, accounting integrity, runtime stability, and deterministic recovery remain ahead of performance optimization.
