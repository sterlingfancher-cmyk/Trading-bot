# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-09-02 19:09 CDT
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Validated runtime-code `main`: `5c4ecdb631c318ecb05dfaf8b8cc29f6d0147e24` (PR #162).
Active stability/accounting/runtime issue: none. Active improvement issue: #157 (shadow-only AI research/adversarial subsystem).

## Communication and Continuity

Keep all Trading-bot progress, blockers, merge notices, runtime findings, and issue-status updates in the currently active main ChatGPT Trading conversation. Do not branch individual issue updates into separate chats unless the user explicitly requests a transition.

Routine bounded stability work should be handled automatically: investigate, repair, test, merge when every required exact-head gate is green, then validate authoritative Splendid deployment evidence. Escalate only genuinely blocked or authority-changing decisions.

## Standing Continuous-Improvement Authorization

The user has authorized one canonical hourly `Trading Continuous Improvement`
task to continue across all current and future demonstrated bug fixes,
reliability/accounting/runtime work, approved shadow-AI upgrades, and
evidence-backed performance improvements. It must not stop or pause merely
because one issue, PR, or upgrade program finishes. The older overlapping
`Trading Issue Watch` task is paused to prevent concurrent automations from
racing on the same repository.

Within paper authority, routine bounded work is pre-authorized and must not wait
for user review or approval:
- investigate demonstrated defects and create/update issues, branches, tests,
  contracts, and PRs;
- inspect exact diffs and repair only demonstrated failures;
- merge automatically only when every required exact-head gate is green;
- validate settled authoritative Splendid evidence after deployment;
- update this handoff after every material finding, design decision, PR, merge,
  runtime result, blocker, or completed stage;
- continue to the next highest-priority safe item.

Performance changes are also pre-authorized only when they satisfy
`VALIDATION_POLICY.md`: baseline-versus-candidate evidence, untouched holdout or
walk-forward testing, realistic costs/slippage, regime and calendar
segmentation, trade-count/turnover/exposure/concentration review, one-variable
ablation, forward shadow or bounded paper canary, all required exact-head CI,
and post-deploy self-check/runtime acceptance. Favorable evidence may be merged
without waiting for routine user approval; unfavorable or inconclusive changes
must not be promoted.

Reserved boundaries still require separate explicit user authorization:
- enabling live trading or changing broker credentials;
- granting AI/ML order, sizing, stop/target, exit, or capital-allocation
  authority;
- relaxing hard daily-loss/drawdown or other hard-risk limits;
- destructive or irreversible canonical, accounting, state, history, day-peak,
  or recovery-evidence changes;
- any expansion beyond the established paper-only authority.

Rules remain sole execution authority and AI/ML remains shadow-only. Escalate
only genuine blockers, missing credentials/authority, destructive actions, or a
proposal that crosses one of the reserved boundaries. Keep all material
user-facing updates in the current main Trading conversation.

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

The authoritative active epoch is `stable-paper-v4-20260826-successor01`. Issue #126 is closed. Its validation hold was formally released on 2026-09-02 through the separate governed gate in Issue #154 and PRs #155–#156; see the release record below.

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

## 2026-09-02 Issue #158 — Released-v4 Legacy Auto-Reconciliation — CLOSED

Fresh settled Splendid startup evidence after validation release proved that the
legacy `paper_accounting_integrity_guard` temporarily auto-reconciled explicit
v4 successor economics during registration. It observed persisted cash/equity
near `13475.004291 / 13475.0`, rebuilt from an incomplete legacy baseline near
`9941.007861`, reported a roughly `3533.9964` discrepancy, and set
`repaired=true` because `validation_hold=false`.

The final successor owner restored the authoritative v4 state. Subsequent
self-check and compact daily audit are clean: cash/equity remain approximately
`13475.004291 / 13475.0`, positions are flat, accounting has zero
coverage/economic issues, the canonical ledger is hash-valid at 55 rows / 9 v4
rows, runner and market-data accounting pass, and there is no lasting capital
corruption.

The demonstrated defect was the transient mutation path: v3+ protection in
`paper_accounting_integrity_guard.py` was incorrectly conditional on the
validation hold. PR #159 keeps all v3+ successor generations
observational/read-only after release while preserving verified-v2 legacy
repair behavior. All four required exact-head workflows passed and PR #159 was
squash-merged as `439c7b1d9675f233ca9d0eff2a54aa04b1780ad9`.

Settled Splendid acceptance after a fresh automatic cycle proved:
- startup detected the incomplete legacy reconstruction but reported
  `successor_accounting_read_only=true`,
  `automatic_repair_suppressed=true`, and `repaired=false`;
- the settled read-only accounting endpoint uses version
  `paper-accounting-integrity-2026-09-02-v3-successor-readonly`, reports
  `overall=pass`, and reconstructs cash/equity `13475.004291`;
- persisted cash/equity remain `13475.004291 / 13475.0`, with no positions;
- accounting coverage/economics are clean and reconstructed open positions are
  empty;
- canonical ledger remains hash-valid at 55 rows / 9 v4 rows;
- market-data accounting is complete at `1381/1381`, with zero in-flight or
  unclassified requests;
- the post-restart automatic cycle succeeded at approximately 14:07:18 CDT
  with no runner error;
- the v4 validation release remains intact;
- the only audit WARN remains the existing elevated-drawdown advisory near
  2.43%, with no halt or self-defense.

Issue #158 is closed. No canonical/history/accounting evidence, risk/day-peak
state, strategy, signals, thresholds, sizing, hard-risk limits, live authority,
ML authority, or order authority changed. Issue #157 is resumed.

## Current Post-Validation Boundary

There is currently no demonstrated canonical/accounting correctness defect,
active runtime endpoint-latency defect, runner error, market-data accounting
gap, or risk halt. The active v4 successor's governed validation hold remains
released on settled evidence.

Post-validation work may proceed under the standing continuous-improvement
authorization. Paper-only authority, immutable canonical/accounting evidence,
hard-risk controls, and rules-only execution authority remain unchanged.

## Immediate Next Action

Continue Issue #157 from completed Stage 3. PR #162 merged the bounded
asynchronous adversarial reviewer, registered but disabled by default with no
provider transport. Proceed to Stage 4 canonical outcome memory and
counterfactual scorecards using read-only immutable execution evidence. Preserve
rules-only authority, exact identity joins, and inconclusive classification for
missing, contradictory, small, or concentrated samples. Continue the scheduled
read-only operational audits.

If a demonstrated bug or higher-priority reliability issue appears, repair it
automatically within the standing boundary, require every exact-head gate,
merge only when green, validate settled authoritative Splendid evidence, and
record the result here. Evaluate performance changes only through
`VALIDATION_POLICY.md`; promote only favorable, reproducible, forward-validated
paper evidence.

Correctness, accounting integrity, runtime stability, and deterministic
recovery remain ahead of performance optimization.

## 2026-09-02 v4 Governed Validation Release — COMPLETE

Issue #154 and PRs #155–#156 added and corrected a separate paper-only,
fail-closed release gate for the exact active epoch
`stable-paper-v4-20260826-successor01`. The historical v1 release module remains
unchanged and cannot release v4. PR #155 was squash-merged as
`8436e73248865a003ae92e0a85aa412029941f32`; PR #156 preserved the exact released
v4 successor shape through legacy startup compatibility and was squash-merged as
`861382ceca2d065cde7b441f19d98471c1779489`.

Both PRs passed the required exact-head Change Safety, Repository
Safety/Performance, Architecture Debt, and full Refactor/Ownership/Configuration/
State/Decision/Runtime/Startup/Research gates. Focused release and successor
compatibility regressions passed locally.

Settled authoritative Splendid acceptance at approximately 13:07 CDT proved:
- bootstrap ready and delegating;
- v4 release endpoint `status=released`, `released=true`,
  `validation_hold=false`;
- epoch `validation_release_status=released`, `validation_released=true`, and
  `forward_validation_required=false`;
- 23 valid exact lifecycle rows, including 19 post-v4 rows;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- accounting coverage complete with zero coverage/economic issues and no
  reconstructed open positions;
- persisted/reconstructed cash and equity within the governed tolerance;
- risk not halted, self-defense inactive, runner healthy, and market-data
  accounting pass.

The compact audit remains WARN only for the existing elevated-drawdown advisory
(`intraday_drawdown_pct` approximately 2.43%); this is not a validation,
accounting, canonical, runner, or market-data blocker. No risk state, canonical
history, day peak/history, strategy, sizing, hard-risk limits, live authority,
ML authority, or order authority changed.

The formal Post-Validation AI gate is now open. Begin with a complete current
repository/code/handoff/ownership/configuration/state/runtime/research review.
Implement the previously approved AI research/adversarial improvements strictly
shadow-only: fail-closed structured AI client, adversarial reviewer, canonical
outcome memory, source/citation and inference-cost telemetry, and AI-vs-rules
counterfactual scorecards. Rules remain sole execution authority.

## 2026-09-02 Pre-Close Operational Audit — WARN / structurally healthy

A fresh settled read-only runtime snapshot at approximately 14:30 CDT, rerun after PR #160 deployment finished registering, proved the authoritative Splendid application ready and delegating with all `11/11` monitored endpoints reachable and no classification failures. The initial automatic artifact captured during registration was rejected as transient deployment evidence and was not treated as a runtime defect.

Settled pre-close evidence:
- self-check `pass`, 9 components checked, no failing components;
- cash/equity `13475.004291 / 13475.0`, no open positions, unrealized P/L `0.0`;
- active epoch `stable-paper-v4-20260826-successor01`, validation hold remains released (`false`);
- accounting `ok`, coverage complete, `coverage_issue_count=0`, `economic_issue_count=0`, reconstructed open positions `[]`;
- canonical ledger append-only/hash-valid at 55 rows, 9 current-v4 rows; latest execution remains BBAI exit `300a83cb7ec14b69884f701ca847ec01`;
- market-data accounting `pass`, `1542/1542` requests classified, zero in-flight/unclassified requests, provider circuit closed;
- runner `pass`, no active error, latest successful automatic run `14:26:21 CDT`, completed cycle `14:26:26 CDT`;
- fresh-day baseline `pass`, no halt, no pending reset;
- risk status `warn` only for elevated intraday drawdown approximately `2.43%`; net daily loss approximately `0.568%`; self-defense inactive;
- profit guard is active because the configured day-profit hard lock had been reached earlier; the current rules result blocks new entries with `entry_block_reason=profit_guard_active` and this is expected configured behavior, not a correctness failure;
- the legacy verified-v2 recovery endpoint still reports raw `fail`, but classification is explicitly non-applicable because the active lineage is v4+ (`superseded_by_active_v4_plus_lineage`); it is nonblocking and does not indicate an active v4 defect.

No new canonical, accounting, runtime, market-data, runner, state, risk-halt, or execution-safety regression was demonstrated. No bug repair or authority change was required. PR #160 Stage 1 is contract/design-only; all four main-branch required workflows passed after merge, including exact Gunicorn startup smoke. Continue Issue #157 Stage 2 shadow-only work under the standing boundary.

## 2026-09-02 Issue #157 Stage 2 — Provider-Neutral Client — COMPLETE

PR #161 added `shadow_ai_research_client.py`, deterministic fake-provider
tests, and the Stage 2 contract/design update. The client is disabled by
default and has no bundled provider SDK, network transport, route, worker,
persistence owner, runtime registration, execution-path hook, or order action.

The client enforces exact request/result cycle, candidate, and input identity;
timezone-aware deadlines; bounded timeout and at most two attempts; retries
only for explicitly transient transport failures; strict `agree`, `reject`, or
`unavailable` decisions; pessimistic complete fallbacks; HTTPS-only citation
normalization with external content marked untrusted; bounded free text and
telemetry; and exact USD cost only when complete configured token-category
pricing is available.

Focused contract/client validation passed 15 tests. Full repository validation
passed across 302 tracked Python files, Railway configuration validation passed,
and the exact diff contained only five intended files. All four required
exact-head PR workflows passed, including the full Refactor/Ownership/
Configuration/State/Decision/Runtime/Startup/Research audit and exact Gunicorn
smoke. PR #161 was squash-merged as
`177ba3a96b25463c01bbc7d76c39c9bd4c1cf4b7`.

Settled authoritative Splendid acceptance after the post-merge restart proved:
- deferred startup completed and the application is ready/delegating;
- self-check is `pass` with no failing components;
- persisted cash/equity remain `13475.004291 / 13475.0`, flat;
- active v4 validation remains released;
- accounting coverage and economics remain clean with no reconstructed open
  positions;
- canonical ledger remains append-only and hash-valid at 55 rows / 9 current-v4
  rows;
- runner remains enabled with no active error and correctly skips after market
  close;
- market-data accounting remains complete with no provider circuit;
- no `/paper/shadow-ai-research-status` route exists (`404`), confirming Stage
  2 did not create a runtime surface;
- the only operational WARN remains elevated drawdown near 2.43%, with no halt
  or self-defense.

No strategy, signal, ranking, selection, sizing, exposure, stop, target, exit,
risk, accounting, canonical/history, state/day-peak, live, ML, or order authority
changed. Issue #157 remains open for Stage 3: a bounded asynchronous adversarial
reviewer extending the existing observer owner, with a single explicitly
started off-thread worker, immutable request snapshots, nonblocking bounded
queue/drop telemetry, and stale-result rejection.

## 2026-09-02 Issue #157 Stage 3 — Asynchronous Reviewer — COMPLETE

PR #162 added shadow_ai_adversarial_reviewer.py and integrated it only through
the existing completed-cycle observer and post-composition runtime registration
owners. It adds no run_cycle wrapper, callable owner, provider transport,
persistence owner, execution route, order callable, or automatic promotion.

The reviewer freezes each bounded candidate request as canonical JSON before
queueing, permits at most 128 queued items and 10 requests per cycle, drops new
research immediately when full, and permits exactly one explicitly started
daemon worker only when reviewer/client/provider configuration is complete.
Provider work cannot run on the execution thread. Late, mismatched, malformed,
or unavailable output is retained only as invalid telemetry and cannot join a
canonical outcome.

Focused client/reviewer/observer/registration validation passed 38 tests.
Repository validation passed across 304 Python files and Railway configuration
validation passed. The first PR head was correctly blocked because a local
timestamp parser duplicated the Stage 2 client helper. The implementation was
narrowed to reuse the existing helper; the architecture-debt delta returned to
zero, all focused tests remained green, and every required exact-head workflow
passed, including Change Safety, Repository Safety/Performance, Architecture
Debt, the full ownership/configuration/state/decision/runtime/startup/research
audit, and exact Gunicorn smoke. PR #162 was squash-merged as
5c4ecdb631c318ecb05dfaf8b8cc29f6d0147e24.

Settled authoritative Splendid evidence after the new process completed
deferred registration proved:
- bootstrap ready/delegating and research isolation active;
- run-report guard v4 installed as the sole final observer owner;
- adversarial reviewer registered with enabled=false, worker_started=false,
  worker_count=0, empty queue/history, and zero provider/request activity;
- execution_waits_for_result=false and every authority mutation flag false;
- self-check pass with no failing components;
- cash/equity 13475.004291 / 13475.0, flat;
- accounting coverage/economics clean, no reconstructed positions;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- v4 validation release intact;
- runner enabled with no active error and correct after-close skip behavior;
- market-data accounting complete with zero unclassified requests and provider
  circuit closed;
- the only audit WARN remains the existing 2.43% drawdown advisory, with no
  halt or self-defense.

No strategy, signal, ranking, selection, sizing, exposure, stop, target, exit,
risk, accounting, canonical/history, state/day-peak, live, ML, or order
authority changed. Issue #157 remains open for Stage 4 canonical outcome memory
and AI-vs-rules counterfactual scorecards.
