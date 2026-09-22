# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-09-19 10:15 CDT
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Validated runtime-code `main`: `d74dede0a82af7b2568531acaa93325bfaf37e33` (PR #261).
Active engineering issue: #84 (authoritative single-owner StateStore / ledger
projection / valuation / risk cutover). Active frozen research issue: #202
(`hold_10d` read-only forward-shadow validation). Issue #222 is safely
reconciled under the verified-flat v5 validation hold; its prior discrepancy
remains unresolved and non-promotable.

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

Issue #157's five implementation stages are complete. Keep its reviewer/client
disabled until provider/model selection, exact token-category pricing,
credentials, and a bounded shadow-only activation/configuration change are
available. Rules remain sole execution authority; forward evidence cannot
self-promote.

Continue the scheduled read-only operational audits. If a demonstrated bug or
higher-priority reliability issue appears, repair it automatically within the
standing boundary, require every exact-head gate, merge only when green,
validate settled authoritative Splendid evidence, and record the result here.
Otherwise select the highest-value evidence-backed performance experiment and
apply `VALIDATION_POLICY.md`; promote only favorable, reproducible,
forward-validated paper evidence.

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

## 2026-09-02 Issue #157 Stage 4 — Canonical Outcome Memory — COMPLETE

PR #163 added `shadow_ai_outcome_memory.py`, focused invariants, and a bounded
change-safety regression selector for the complete shadow-AI subsystem. The
module is a pure read-only research library: it adds no runtime hook, route,
worker, provider transport, persistence owner, state save, canonical-ledger
reader/writer, execution input, or automatic promotion mechanism.

The memory accepts only already-derived, integrity-qualified outcomes keyed by
an immutable canonical execution ID. Canonical source IDs must include the
primary ID; path evidence must be valid and training-eligible; MFE, MAE,
realized return, entry notional, holding period, and declared comparison
dimensions must be complete and finite. Identical duplicates deduplicate, while
contradictory rows sharing an execution ID are entirely excluded. Comparable
retrieval requires the same side and uses deterministic strategy/setup/regime/
sector/bucket/volatility/session/signal similarity.

Counterfactual scorecards require an explicit one-to-one binding across exact
`cycle_id`, `candidate_id`, `input_fingerprint`, and canonical execution ID;
symbol/time inference is forbidden. They compare the realized rules P&L with
the shadow agree/reject outcome and subtract exact inference cost. Missing cost
leaves net metrics null. Small, concentrated, incomplete, duplicate, missing,
or contradictory samples remain inconclusive; sufficient diverse evidence is
still labeled observational-only and can never self-promote.

The impact-aware gate now automatically runs the research contract, client,
reviewer, and outcome-memory tests whenever any `shadow_ai_*` implementation or
test changes. Local exact-head validation passed 97 core and shadow regressions,
repository/Railway validation, and all structural ownership/configuration/debt
checks with zero new critical findings or warnings. All four required PR gates
then passed on remote head `7e5f538b6c29c433787b6106b4c34600fa7db2df`.
PR #163 was squash-merged as
`a191af92b9e52ab4e8324911e1b9dac563452518`.

Settled authoritative Splendid evidence on that exact deployed commit proved:
- bootstrap ready and delegating;
- deployment commit exactly `a191af92b9e52ab4e8324911e1b9dac563452518`;
- self-check `pass`;
- cash/equity `13475.004291 / 13475.0`, no positions;
- accounting coverage complete with zero coverage/economic issues and no
  reconstructed open positions;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- v4 validation release remains intact with `validation_hold=false`;
- runner enabled with no active error and correct after-close skips;
- risk not halted and self-defense inactive;
- compact audit WARN remains only the existing 2.43% drawdown advisory.

No strategy, signal, ranking, selection, sizing, exposure, stop, target, exit,
risk, accounting, canonical/history, state/day-peak, live, ML, or order authority
changed. Issue #157 remains open for Stage 5: bounded read-only observability,
source/cost/fallback evidence, state-size/restart checks, and forward shadow
validation. A provider transport and any reviewer enablement remain separate,
explicit configuration work; rules remain sole execution authority.

## 2026-09-03 Issue #157 Stage 5 — Bounded Observability — COMPLETE

PR #164 added a separate, bounded research-evidence store and the read-only
`/paper/shadow-ai-research-status` surface. The store is not portfolio state or
canonical execution evidence. It retains at most 500 records, 32 KB per record,
and 8 MB overall; uses canonical JSON, SHA-256 checksum validation, atomic
replacement, exact cycle/candidate/input identities, and idempotent duplicate
handling; and fails closed without overwriting corrupt or contradictory data.
Full prompts, raw reasoning/source bodies, secrets, authorization, credentials,
and token values are rejected recursively.

Completed reviewer records can be persisted from the existing asynchronous
worker, never from the execution thread. Persistence failure is telemetry-only
and cannot stop the worker or affect the rules result. The status surface reports
decision/provider/model counts, sources and citations, fallbacks, token
categories, exact inference cost coverage, store size/integrity/restart state,
and forward-evidence readiness. Readiness requires an enabled/live reviewer,
restart-valid evidence, at least 100 exact join-eligible results, no more than
20% unavailable results, and complete exact-cost coverage. Meeting those
diagnostics never authorizes promotion or any execution behavior.

The client and reviewer remain disabled by default and no provider transport was
added. The impact-aware Change Safety gate now automatically runs the complete
contract/client/reviewer/outcome-memory/evidence-store/observability regression
set for every future `shadow_ai_*` change. Local validation passed 74 focused
tests, repository/Railway validation across 312 Python files, and structural,
ownership, typed-configuration, and debt checks with zero new critical findings
or warnings. All four required exact-head workflows passed on
`e8dd69e845e363d26a1b854b0b343fe4b8473605`. PR #164 was squash-merged as
`492ccd0136b4499a1f85b77ef0ba52944fe826ae`.

Settled authoritative Splendid evidence on the exact deployed merge proved:
- bootstrap `ready` and delegating;
- deployment commit exactly `492ccd0136b4499a1f85b77ef0ba52944fe826ae`;
- self-check `pass` with 9 passed components, 1 deferred research component,
  zero warnings/failures, and no next action;
- Stage 5 route `pass`, restart-loadable store with valid integrity, zero bytes/
  records/writes, and no rejected evidence;
- reviewer disabled with zero workers, cycles, candidates, requests, provider
  calls, results, persistence attempts, fallbacks, tokens, or inference cost;
- cash/equity `13475.004291 / 13475.0`, no positions;
- bidirectional accounting coverage complete with zero coverage/economic issues
  and reconstructed cash/equity `13475.004291 / 13475.004291`;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- v4 validation remains released with `validation_hold=false`;
- auto runner enabled, thread active, no current error, and normal premarket
  closed-session skips;
- risk not halted, self-defense inactive, and daily audit `pass` (11/11).

No strategy, signal, ranking, selection, sizing, exposure, stop, target, exit,
risk, accounting, canonical/history, state/day-peak, live, ML, or order authority
changed. Issue #157's five implementation stages are complete. Beginning paid
forward evidence still requires a separately selected provider/model, exact
pricing, credentials, and an explicit bounded enablement/configuration change;
it remains shadow-only and can never self-promote. Continuous improvement should
otherwise proceed to demonstrated correctness defects first, then the highest-
value evidence-backed performance work under `VALIDATION_POLICY.md`.


## 2026-09-03 Issue #165 — Concurrent State Serialization / Stale Runner Error — CLOSED

A handoff-only restart after Stage 5 exposed a real, previously observed runner
failure: the first automatic cycle raised `dictionary changed size during
iteration`. Later premarket closed-session cycles completed, but the old error
remained classified as active, causing self-check WARN and compact daily-audit
FAIL despite successful recovery.

The bounded root cause had two parts. `atomic_json_write` streamed a live nested
state dictionary directly through `json.dump`, so concurrent watchdog mutation
could invalidate iteration. Separately, the cycle-completion owner did not clear
an active runner error after a later cycle returned successfully or completed an
expected closed-market skip.

PR #166 now pre-serializes a stable JSON snapshot before opening/replacing the
state file, retries only the two recognized concurrent-dictionary mutation
errors up to five bounded attempts, and otherwise fails closed. A successfully
completed cycle preserves the prior failure as recovered forensic evidence and
then clears only the active runner-error fields; a failed cycle never clears an
error. Four focused regressions cover retry/success, bounded failure, successful
recovery, and failure retention. Repository/Railway/structural/ownership/
configuration/debt validation passed, and all four required exact-head workflows
passed on `ac0ae3012b8af6f78fec020a15825604b02dea85`. PR #166 was squash-merged
as `1efd939c8906aefa1e19b7d8df1a6047357094e2`.

Settled authoritative Splendid acceptance after a fresh startup and automatic
premarket closed-session cycle proved:
- exact deployed commit `1efd939c8906aefa1e19b7d8df1a6047357094e2`;
- bootstrap ready/delegating;
- runner enabled with a completed automatic cycle, `last_error=null`, and the
  historical dictionary-mutation failure retained as `last_recovered_error`;
- state I/O version
  `state-io-hardening-2026-09-03-v2-stable-serialization`, valid state,
  stable pre-serialization, five bounded mutation retries, atomic save, and no
  overlapping run cycle;
- self-check `pass` and compact daily audit `pass` at 11/11;
- cash/equity `13475.004291 / 13475.0`, no positions;
- bidirectional accounting coverage complete with zero coverage/economic issues;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- v4 validation release intact with `validation_hold=false`;
- risk not halted, self-defense inactive, and market-data accounting complete;
- Stage 5 research status `pass`, with the reviewer still disabled, zero
  workers/provider calls/results/cost, and a valid restart-loadable empty store.

No canonical/accounting/history/day-peak evidence, strategy, signals, ranking,
sizing, exposure, hard-risk limit, live authority, ML authority, or order
authority changed. Issue #165 is closed.

## 2026-09-03 Issue #167 — Forward Performance Evidence Integrity — CLOSED

Fresh authoritative forward-shadow research exposed catastrophic transient marks
that had been retained as durable MFE/MAE evidence. Although current prices and
horizon returns were near entry, VZLA reported MFE above 10,800%, SRPT above
6,700%, and the balanced aggregate reported average MFE/MAE of +329.2547% /
-64.4054%. Trading, accounting, canonical, runner, market-data, and risk state
remained healthy; the demonstrated defect was confined to research-evidence
integrity and blocked any performance promotion.

PR #168 reuses the established symmetric 0.40x..2.50x source-integrity envelope
against the immutable shadow entry price before updating excursions or resolving
horizons. Catastrophic marks can no longer overwrite the last trusted mark or
outcomes; only bounded rejection reason/ratio telemetry is retained. Existing
contaminated rows are classified read-only and excluded from aggregates, actual-
entry counts, and missed-candidate comparisons without rewriting historical
evidence. Forward summaries now expose eligible/excluded counts, exclusion
reasons, and `historical_rows_rewritten=false`; evidence remains explicitly
`inconclusive` and `promotion_eligible=false` whenever contamination is present.
Four focused regressions cover long and short rejection, valid resolution, and
read-only legacy exclusion, and the Change Safety gate now selects them for every
future performance-evidence integrity change.

Local focused and canonical validation passed 80 tests plus repository/Railway/
structural/ownership/configuration/debt validation with zero new critical findings
or warnings. The exact four-file diff passed all four required exact-head
workflows on `cc4c9e6f863d2261ed99301748536c5e0b9bc829`. PR #168 was squash-
merged as `3660942dd9e04024f0080bfdc58df9ee077fec3a`.

Settled authoritative Splendid evidence on the exact deployed merge proved:
- bootstrap ready/delegating and deployment commit exactly `3660942dd9e04024f0080bfdc58df9ee077fec3a`;
- forward evidence v2 retained all 1,200 rows, classified 998 eligible and 202
  excluded as `stored_excursion_outside_source_envelope`, and rewrote none;
- the eligible balanced aggregate is bounded at average MFE +2.8618% and MAE
  -3.0585%, while promotion remains false and evidence remains inconclusive;
- self-check `pass` with 9 passed components, only performance evidence deferred,
  zero warnings/failures, and no next action;
- compact daily audit `pass` at 11/11 and market-data accounting complete;
- bidirectional accounting coverage complete with zero coverage/economic issues
  and reconstructed cash/equity `13475.004291 / 13475.004291`;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- v4 validation release intact with `validation_hold=false`;
- runner enabled with fresh automatic premarket skips and no active error;
- risk not halted, self-defense inactive, and intraday/daily loss metrics zero.

No strategy, signal, ranking, selection, sizing, exposure, stop, target, exit,
risk, accounting, canonical/history, state/day-peak, live, ML, or order authority
changed. Issue #167 is closed. Future performance work must use only integrity-
eligible evidence and continue to satisfy `VALIDATION_POLICY.md` before promotion.

## 2026-09-03 Issue #96 — Read-Only Runtime Sentinel Stage — COMPLETE

The repository already contained a deterministic offline `system_sentinel`
classifier, but it was not connected to authoritative runtime diagnostics. PR
#169 added the on-demand read-only `/paper/system-sentinel-status` route. It
composes existing valuation, bidirectional-accounting, canonical-ledger, risk,
startup, runner, and market-data diagnostics into deterministic advisory
incidents with evidence, suspected cause, confidence, bounded repair guidance,
and a test plan that always retains the mandatory core invariant suite.
Configuration and architecture remain CI-observed rather than runtime-derived,
and that coverage split is explicit in the response.

The sentinel starts no worker and is outside the run-cycle and execution paths.
It performs no repair, persistence, state/canonical/accounting/history mutation,
halt clearing, GitHub issue/PR write, or automatic merge. A bounded collector
failure is reported as advisory WARN without affecting the application. The
runtime adapter also preserves the established provider-accounting rule that one
concurrent in-flight request is not a false incident when aggregate market-data
status passes. Future sentinel changes automatically select both sentinel
regression suites through Change Safety.

The first PR head `c85d81a6afe37a6867401973aa69e383f06bca28` was correctly
blocked because Architecture Debt detected a two-module import cycle. Nothing
merged. The revised implementation removed that cycle through an adapter-owned
installation-status record. Local validation passed 99 focused/core tests,
repository/Railway validation, and structural/ownership/configuration/debt checks
with zero new critical findings or warnings. All four required exact-head gates
passed on `bff6b8b34b48997240b182a82fe1d313a5034169`; PR #169 was
squash-merged as `6986f00fd2c38ab9be898eded5b5cb6e47904d84`.

Settled authoritative Splendid evidence on the exact merge proved:
- bootstrap ready/delegating and exact deployment commit `6986f00fd2c38ab9be898eded5b5cb6e47904d84`;
- sentinel `quiet/pass`, zero incidents, zero collector errors, valid positive
  valuation, clean accounting, valid ledger, ready startup, healthy runner/risk,
  and complete market-data accounting;
- self-check `pass` with 9 passed components, only performance evidence deferred,
  zero warnings/failures, and no next action;
- compact daily audit `pass` at 11/11;
- bidirectional accounting complete with zero coverage/economic issues and
  reconstructed cash/equity `13475.004291 / 13475.004291`;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- v4 validation release intact with `validation_hold=false`;
- no active runner error, risk halt, or self-defense.

No strategy, signal, ranking, sizing, exposure, risk limit, accounting, canonical/
history, state/day-peak, live, ML, or order authority changed. Issue #96 is closed;
automated repair/self-healing remains disabled, and any future GitHub issue or
draft-PR output must remain advisory and auditable.

## 2026-09-03 Issue #170 — Performance Audit V2 Signal-ATR Integrity — COMPLETE

The continuous performance-evidence review found that Performance Audit V2
correctly queued entry signals at the session close and filled them at the next
session open, but derived the initial stop from the execution session's completed
ATR. That ATR includes the execution day's High/Low/Close, which is unavailable
at its opening print and therefore introduced forward-looking information into
the simulated stop path.

PR #171 binds ATR when the signal is queued and derives the next-open initial stop
only from that signal-time value. Missing or invalid signal ATR falls back to the
configured policy stop, and each simulated entry records both `signal_atr_pct`
and `initial_stop_pct` for evidence auditability. Three focused regressions prove
that execution-day range cannot widen the stop, signal-time ATR controls it, and
missing signal ATR fails closed. Change Safety now automatically runs both
performance-evidence integrity suites for changes to either audit lab.

Local exact-head Change Safety passed 69 selected core/integrity tests with zero
failures or new critical findings. All four required GitHub exact-head gates
passed on `f23631d2693696b9984dacecbaacfc27a4360557`; PR #171 was
squash-merged as `e7bdced96ac17b781b6c76df9c34ab159c5498ea`, and Issue #170
closed automatically.

Settled authoritative Splendid evidence on the exact merge proved:
- bootstrap ready/delegating and exact deployed commit `e7bdced96ac17b781b6c76df9c34ab159c5498ea`;
- sentinel `quiet/pass` with zero incidents and collection errors;
- self-check `pass` with 9 passed components, one deferred performance-evidence
  component, and no warning, failure, or next action;
- compact daily audit `pass` at 11/11;
- bidirectional accounting complete with zero coverage/economic issues and
  reconstructed cash/equity `13475.004291 / 13475.004291`;
- canonical ledger append-only/hash-valid at 55 rows / 9 current-v4 rows;
- v4 validation remains released with `validation_hold=false`;
- runner, market-data accounting, valuation, and risk remain healthy with no
  active error, halt, or self-defense.

No historical evidence was rewritten and no prior result is automatically
promoted. Future Performance Audit V2 runs will use the corrected signal-time ATR
semantics, and any performance change remains subject to the complete validation
and forward-shadow policy. No strategy, signal, ranking, sizing, exposure, risk
limit, canonical/accounting/history, state/day-peak, live, ML, or order authority
changed.

## 2026-09-03 09:33 CDT Morning Operational Audit — PASS

A fresh rerun of the existing read-only runtime-research snapshot against the fully settled authoritative Splendid deployment completed successfully after the morning market opened. The repository runtime code remains PR #171 / `e7bdced96ac17b781b6c76df9c34ab159c5498ea`; current `main` additionally contains documentation-only commit `c74386ab0e4776f0fe04136dbafc0177fd32a04d`.

Fresh evidence proves:
- application ready, bootstrap `ready`, phase `delegating`, and all `11/11` monitored endpoints reachable with no required classification failures;
- self-check and compact daily audit both `pass`;
- active epoch remains `stable-paper-v4-20260826-successor01` with governed validation released (`validation_hold=false`);
- persisted cash/equity approximately `11453.727291 / 13477.61`, with two open short positions: MU and STX; unrealized P/L approximately `+2.60` and realized-today `0.0`;
- bidirectional accounting coverage is complete with `coverage_issue_count=0`, `economic_issue_count=0`, reconstructed cash/equity approximately `11453.726919 / 13477.607359`, and reconstructed open positions exactly `MU` and `STX`;
- canonical execution ledger remains append-only/hash-valid at `57` total rows / `11` current-v4 rows, with zero parse/hash errors; the two new rows are the exact MU and STX short entries;
- independent Alpaca IEX snapshots around 09:33 CDT show MU around `931.96` with a roughly `930.94/932.19` quote and STX around `777.80` with a roughly `775/781` quote, confirming the paper marks/entries are market-plausible rather than catastrophic quote outliers;
- market-data accounting `pass` with `5650/5650` requests classified, zero in-flight/unclassified requests, and provider circuit closed;
- runner `pass`, enabled, no active error, latest successful automatic run `09:29:22 CDT`, latest completed cycle approximately `09:29:28 CDT`;
- fresh-day baseline `pass`: day start equity `13475.004291`, day peak equity approximately `13477.607362`, no halt, zero reported daily loss/drawdown at capture time, and self-defense inactive;
- system/runtime state presents no new canonical, accounting, market-data, runner, valuation, or risk-safety regression.

Issue #170 remains fixed/closed and its signal-time ATR research-evidence correction is deployed. No bug repair, state mutation, authority change, or user action was required by this audit. Continue normal scheduled audits and evidence-backed performance/shadow-AI work under the standing boundaries.

## 2026-09-04 Pre-Close Operational Audit — PAPER-ONLY Continuity Append

Append-only record for the pre-close operational audit captured around 2026-09-04 14:35–14:36 CDT. Continuity facts appended here (paper-only tooling changes visible in repository main):

- repository main current head: commit eb78ee88d3365bd8988addf0e967b6af48f83d46 (merged PR #178). PR #177 fixed the original protected-path contradiction; PR #178 replaced large-file reproduction with a bounded byte-preserving append mode. Both changes are paper-only continuity tooling.
- PR #178 exact-head Change Safety, Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, and full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit (including exact Gunicorn startup smoke) all passed.
- Settled authoritative Splendid evidence (capture ~2026-09-04 14:35–14:36 CDT):
  - application ready, phase `delegating`, all 11/11 monitored endpoints reachable;
  - account cash/equity approximately 13412.285098 / 13412.29, no open positions; realized-today ≈ -29.94, unrealized 0;
  - canonical execution ledger append-only at 71 rows, hash chain valid, active epoch `stable-paper-v4-20260826-successor01`;
  - active bidirectional accounting coverage complete: coverage_issue_count=0, economic_issue_count=0, reconstructed cash/equity ≈ 13412.285089 and flat positions;
  - runner enabled with no active error; latest successful cycle ≈ 14:31:41 CDT;
  - provider accounting complete: 41,117 requests, 41,116 successes, 1 empty/failure, 0 timeouts, 0 unclassified, circuit closed;
  - risk not halted; intraday drawdown ≈ 0.243% and net daily loss ≈ 0.223%; the compact daily audit overall `FAIL` is solely the intentional final-30-minute self-defense entry block (this is not a loss/canonical/accounting/runtime failure);
  - fresh-day baseline `pass`; legacy v2 recovery diagnostic non-applicable under active v4 lineage;
  - recent morning positions GEV / NVDA / ORCL / OKTA / CRDO exited via `market_regime_protection` and are represented in canonical/state evidence; no canonical/state divergence observed.
- No strategy, signal, sizing, hard-risk, account-state, canonical-history, live-authority, or ML-authority change occurred.

After this append-only handoff PR is verified and merged, Issue #176 will be complete.

## 2026-09-08 Morning Audit

- repository main current head: commit 70aaaec992f0ca160ac603f8e70aabcc6614eef2
- fresh Splendid capture ~09:41 CDT — PASS:
  - cash 13412.285098055443, equity 13412.29, flat positions
  - canonical ledger chain valid: 71 rows / 25 current-v4 rows
  - coverage/economic issues: 0
  - market-data classified: 67855/67855
  - runner healthy; last successful automatic run 09:40:26 CDT
  - risk not halted (unhalted)
- Issue #181 (holiday-session defect) remains open because app.py market_clock still lacks exchange-holiday gating
- Fourth bounded repair was attempted twice; both repo-agent calls timed out at 180 seconds before any edits or PR, so no repository mutation occurred
- Next action: follow a safe repair path avoiding oversized repo-agent context, then apply a surgical holiday guard change with focused regressions, run all mandatory exact-head gates, and perform Splendid post-deploy validation

## 2026-09-08 Issue #193 — Isolated Performance Audit V2 Baseline — COMPLETE

Issue #181's holiday-session defect was subsequently repaired and closed by PR
#189 before this performance stage began. Fresh repository and authoritative
runtime inspection then confirmed that Performance Audit V2 had never run and
that the existing async launcher was intentionally not registered because it
would execute heavy research inside the production Splendid process.

PR #194 added a standalone research-process adapter with atomic JSON state,
durable core and per-ablation checkpoints, explicit resume, bounded inputs, and
no Flask, paper-runner, broker, production-state, or order surface. It also added
a concurrency-guarded GitHub Actions workflow and focused isolation, resume, and
fail-closed regressions to mandatory Change Safety selection. All four exact-head
gates passed on `4b7dc7e4ec4b2542c12e2fb8ac516425d657e5fc`; the PR was
squash-merged as `0bcf724e51b4ded3e0f58896ac2cef1e2a189df3`.

PR #195 added a narrowly scoped, repository-tracked request that launches one
isolated research job only when that request changes on `main`. Request fields
are validated before use, fixed concurrency prevents overlapping duplicate jobs,
and manual dispatch/resume remains available. All four exact-head gates passed
on `6a3b87cf6da73884284611418233cb9194d8d6e8`; the PR was squash-merged
as `a91250d8d749fa150d8d6a05e0c2a9786159f201`.

Isolated workflow run `34288938589` completed successfully and produced artifact
`performance-audit-v2-evidence` with digest
`sha256:a3c6ee812672c142bf3f00eb1083f7b725eb4404f824e18a6f332b1a8142bb3a`.
The result is bound to source commit `a91250d8d749fa150d8d6a05e0c2a9786159f201`
and covers 1,254 sessions from 2021-09-09 through 2026-09-08, all 45 requested
symbols, 15 rolling test folds per profile, 8 bps modeled transaction cost, and
18 one-variable ablations. Signal-time ATR integrity from Issue #170 remains in
force.

Material baseline results:
- current-policy proxy: +67.52% total return, 10.92% CAGR, 21.13% maximum
  drawdown, 0.671 Sharpe, 467 trades, and 25.44% average exposure;
- SPY buy-and-hold: +82.53%, 12.85% CAGR, 24.50% maximum drawdown, and 0.789
  Sharpe;
- permissive profile: +249.55% with 31.10% maximum drawdown, but -49.82% in
  the defensive regime with 52.72% regime drawdown;
- adaptive profile: +74.37% with 20.33% maximum drawdown and 0.643 Sharpe,
  including a -16.66% worst rolling test fold and -34.38% defensive-regime
  return;
- the highest full-sample ablation objective was `max_positions_2`, at +63.46%
  return, 13.46% maximum drawdown, 0.756 Sharpe, and 441 trades. This is an
  adaptive research-proxy result, not authority to alter the runtime policy.

No candidate was promoted. The baseline exposes only one cost assumption and
does not yet report turnover, gross traded notional, contribution concentration,
capacity/liquidity stress, or delayed-execution sensitivity. Issue #196 tracks
those required evidence-integrity additions and a new versioned baseline before
one candidate may be selected for separate forward shadow evaluation.

Fresh settled Splendid evidence after both merges remained clean: application
ready/delegating with 11/11 endpoints reachable; self-check and compact daily
audit pass; cash/equity approximately `13412.285098 / 13412.29`, flat positions;
bidirectional accounting coverage complete with zero coverage/economic issues;
canonical ledger append-only/hash-valid at 71 rows / 25 current-v4 rows; v4
validation released; runner, market-data accounting, valuation, and risk healthy
with no active error, halt, or self-defense. V2 remains disabled/not-run inside
Splendid, as required; its completed evidence exists only in the isolated
research artifact.

No strategy, signal, ranking, selection, sizing, exposure, stop, exit, hard-risk
limit, canonical/accounting/history, state/day-peak, live, ML, AI, or order
authority changed. Issue #193 is closed; Issue #196 is the active bounded
performance-research item.

## 2026-09-08 Issue #198 — V2 Per-Symbol ATR Binding — COMPLETE

Post-baseline code review found that `_simulate_next_open()` queued each selected
candidate with `signal_atr_pct` from the final universe-scan row rather than the
selected candidate's own row. The first Issue #193 artifact remains immutable,
but its results are quarantined from candidate selection because per-symbol stop
distances were therefore not trustworthy.

PR #199 changed only that binding, added a two-symbol regression proving distinct
signal ATR values survive ranking and next-open stop construction, and advanced
the bounded isolated-research request. All four required exact-head gates passed
on `bb5d0181d5af152e246fe34399f827cf19c5294a`; the PR was squash-merged as
`0d38d4590cfee0e16bd15acd031991e053322bc6`. Post-merge main gates also passed.

Isolated workflow run `34290415322` completed successfully and produced corrected
artifact `performance-audit-v2-evidence` (`10081194751`) with digest
`sha256:4333b2783d3348d4cb093080aa466ccd56f40f836a75704b044d6c1606e179ef`.
It is bound to the merge commit and covers the same 1,254 sessions, 2021-09-09
through 2026-09-08, and all 45 requested symbols with no provider errors.

The correction materially changed the research conclusions:
- current-policy proxy: +65.03% total return, 10.59% CAGR, 25.40% maximum
  drawdown, 0.618 Sharpe, and 479 trades; rolling out-of-sample return +146.00%,
  OOS Sharpe 1.288, and 73.33% positive folds;
- adaptive-balanced: +95.90% total return, 14.47% CAGR, 25.49% maximum drawdown,
  0.726 Sharpe, and 650 trades; rolling OOS return +213.91%, OOS Sharpe 1.399,
  and 73.33% positive folds;
- balanced-static: +194.58% total return, 24.25% CAGR, 25.35% maximum drawdown,
  0.955 Sharpe, and 773 trades;
- permissive: +319.71% total return, 33.41% CAGR, 31.56% maximum drawdown,
  1.086 Sharpe, and 1,160 trades.

The best full-sample one-variable ablation changed from `max_positions_2` to
`hold_10d`: +136.28% total return, 20.89% maximum drawdown, 0.887 Sharpe,
626 trades, and 31.22% average exposure. This is not a promotion decision.
Issue #196 still requires multi-cost/slippage, turnover and traded-notional,
concentration, capacity/liquidity, and delayed-execution evidence before a single
candidate can advance to forward shadow testing.

Fresh settled Splendid evidence after deployment remains clean: ready/delegating,
11/11 endpoints reachable, self-check pass, daily audit pass, flat account at
approximately `13412.285098 / 13412.29` cash/equity, zero accounting coverage or
economic issues, 71-row hash-valid canonical ledger, released v4 validation,
healthy runner and market data, and no halt or self-defense. Production V2 remains
disabled/not-run as required; only the isolated artifact holds this research.

No production strategy, signal, selection, sizing, exposure, stop, exit, risk
limit, canonical/accounting/history, state/day-peak, live, AI/ML, broker, or order
authority changed. Issue #198 is closed; Issue #196 remains the active performance
evidence-integrity stage.

## 2026-09-08 Issue #196 — V2 Validation Evidence and Candidate Selection — COMPLETE

PR #201 added the previously missing offline validation evidence: per-side cost
sensitivity at 4/8/15/25 bps, one/two/three-session delayed-open execution,
turnover and gross traded notional, signal-time 20-session average-dollar-volume
capacity stress, symbol and sector-group contribution concentration, and a
fail-closed evidence-completeness verdict. It also rejects stale-engine resumable
checkpoints and makes the focused Issue #196 suite mandatory in Change Safety.
The work has no broker, order, paper-runner, production-worker, state, or trading
authority. All four exact-head gates passed on
`258f8dab5e65627ebeef13861afaa301c17442a1`; PR #201 was squash-merged as
`8df2deb420df58e505408f45942b89ca4b01b7f1`.

Isolated workflow run `34309177709` completed successfully and produced artifact
`performance-audit-v2-evidence` (`10087800214`), locally verified as
`sha256:0f354314f1fde9456ce98be79c3c0e79dbc8f45c97d1b2f6073599e32ec5a795`.
It is bound to the merge commit and covers all 45 requested symbols and 1,254
sessions from 2021-09-09 through 2026-09-08. The evidence verdict is complete,
its missing list is empty, and automatic promotion remains false.

The adaptive baseline remains +95.89% total return, 14.47% CAGR, 25.49% maximum
drawdown, 0.726 Sharpe, and 650 trades. Its modeled 8-bps-per-side fees are
`$1,707.16` and annualized turnover is `35.318x`. The highest-value one-variable
candidate remains `hold_10d`: +136.28% return, 18.86% CAGR, 20.89% maximum
drawdown, 0.887 Sharpe, 626 trades, `$1,761.19` modeled fees, and `34.191x`
annualized turnover.

The candidate remains profitable under the bounded stresses: at 25 bps per side
it reports +78.21% return, 12.31% CAGR, 22.45% maximum drawdown, and 0.630
Sharpe; two- and three-session delayed execution report +231.55% and +158.29%
respectively. At `$10,000`, no entry exceeds the 1% ADV participation limit.
The worst historical entry estimates capacity near `$38,384.59` before crossing
that limit; three of 626 entries exceed it at `$100,000` and 30 at `$1,000,000`.

Concentration is material and prevents casual promotion: MU contributes 19.55%
of absolute symbol P&L; semiconductors contribute 37.58% of absolute sector-group
P&L; semiconductors plus crypto equities contribute 61.82%. `hold_10d` is selected
only as the next research candidate. Issue #202 owns candidate-specific rolling
walk-forward/untouched-holdout, calendar, regime, concentration/capacity, and
forward-shadow exit-counterfactual validation. No runtime hold period changed.

Fresh settled Splendid evidence after deployment passes: ready/delegating,
self-check and daily audit pass, flat cash/equity approximately
`13412.285098 / 13412.29`, zero accounting coverage/economic issues, 71-row
hash-valid canonical ledger, released v4 validation, healthy runner/market data/
risk, and no halt or self-defense. Production V2 remains disabled/not-run.

No production strategy, signal, ranking, selection, sizing, exposure, stop, exit,
hard-risk limit, canonical/accounting/history, state/day-peak, live, AI/ML,
broker, or order authority changed. Issue #196 is complete; Issue #202 is the
active bounded performance-validation stage.

## 2026-09-08 Issue #202 Stage 1 — Candidate-Specific Historical Validation — COMPLETE

PR #204 added dedicated historical validation for the selected `hold_10d`
candidate: fixed-policy rolling walk-forward, calendar-year and regime reports,
plus its existing cost/delay, turnover, capacity, and concentration diagnostics.
The evidence explicitly records that the candidate was selected after inspecting
the full history, so there is no untouched post-selection holdout. Forward shadow
confirmation remains mandatory and automatic promotion remains impossible. Two
focused regressions were added to the mandatory performance-evidence suite.

All four exact-head gates passed on
`afa885a11a31ae4625a9025804a9f8e06a9d95a0`; PR #204 was squash-merged as
`99299c0b00f6baba2a5d0d2b5a06a0d6073e3a47`. Isolated workflow run
`34310508489` completed successfully and produced artifact
`performance-audit-v2-evidence` (`10088262578`), locally verified as
`sha256:b48f8a8983065154186510c2a1f7243cafc5888c2358b96ed4cf75b50229cbc6`.
It covers all 45 requested symbols and 1,254 sessions from 2021-09-09 through
2026-09-08 with a complete candidate-historical-validation verdict and empty
missing list.

The candidate's full-sample result remains +136.28% total return, 18.86% CAGR,
20.89% maximum drawdown, 0.887 Sharpe, and 626 trades. Its fixed-policy rolling
walk-forward report formally passes: 15 folds, 10 positive folds (66.67%),
+236.32% combined OOS return, 1.486 OOS Sharpe, 23.20% combined OOS drawdown,
and 16.20% worst-fold drawdown. Calendar results are negative in partial 2021
and 2022, then positive in 2023-2026.

Regime weakness remains material: constructive -4.87%, defensive -35.13%, and
neutral -24.29%, versus risk-off +2.67%, risk-on +233.05%, and strong-risk-on
+47.90%. This reinforces the need for representative forward evidence and bars
any direct promotion from the historical result.

Fresh settled Splendid evidence after deployment passes: ready/delegating,
self-check and daily audit pass, flat cash/equity approximately
`13412.285098 / 13412.29`, zero accounting coverage/economic issues, 71-row
hash-valid canonical ledger, released v4 validation, healthy runner/market data/
risk, and no halt or self-defense. Production V2 remains disabled/not-run.

No production strategy, signal, ranking, selection, sizing, exposure, stop, exit,
hold period, hard-risk limit, canonical/accounting/history, state/day-peak, live,
AI/ML, broker, or order authority changed. Issue #202 remains open for Stage 2:
a read-only forward-shadow exit comparator with predeclared promotion criteria.

## 2026-09-09 Issue #202 Stage 2 — Frozen Forward-Shadow Comparator — ACTIVE

PR #206 added the isolated forward-shadow comparator for the already-selected
`hold_10d` candidate. The candidate, observation boundary, costs, matching rules,
and all acceptance criteria were frozen before any forward observation could
influence them. All four required exact-head gates passed on
`207f40278ac14960c7252e9af7205c3e2a223a28`; PR #206 was squash-merged as
`7c79bbf15e6d7a2b7de15919b101caf8a0a24ccc`.

The frozen contract requires at least 100 exact matched completed lifecycles, 30
genuine exit divergences, 60 forward sessions across three calendar months, 20
neutral entries, 20 defensive/risk-off entries, at least 60% exact pairing
coverage, no symbol above 25%, positive mean net delta at 8 bps per side,
nonnegative mean net delta at 25 bps, and nonnegative neutral and
defensive/risk-off deltas. Malformed, ambiguous, contradictory, overlapping, or
concentrated evidence fails closed. Automatic promotion is impossible.

The comparator fully recomputes evidence from preserved V2 simulation rows. It
has no production import, worker, provider call, state/file write, broker/order
path, exit blocker, risk/strategy authority, AI/ML authority, or automatic
promotion path. The production holding period remains unchanged.

Settled authoritative Splendid acceptance on the merge commit passes: sentinel
`quiet/pass` with zero incidents or collection errors; self-check and daily audit
pass; the account is flat at approximately `13412.285098 / 13412.29`
cash/equity; accounting has zero coverage/economic issues; the canonical ledger
is append-only and hash-valid at 71 rows / 25 current-v4 rows; v4 validation is
released; startup, runner, market data, valuation, and risk are healthy with no
halt or active runner error.

The engine-version change correctly invalidated stale persisted V2 results on
Splendid, whose read-only status is now `not_run`. Do not use the production web
route to rebuild them. The next bounded step is a fresh five-year, 45-symbol
isolated workflow run, then collection of forward observations under the frozen
contract. Until the sample, duration, regime, coverage, concentration, and
economic gates all pass, Issue #202 remains open and the candidate remains
research-only.

## 2026-09-09 Issue #208 — Isolated Frozen-Candidate Binding — CLOSED

The first Stage 2 isolated artifact (workflow `34331189684`, artifact
`10095961318`, digest
`sha256:968a75a9fb3cc1f50d157f03d32736304f12f3fa284118b5f7afcdb2afa0a137`)
correctly started at zero post-freeze observations, but inspection found that the
resumable runner still passed the dynamically top-ranked ablation map into the
candidate validator. The current ranking happened to select `hold_10d`, so its
numbers were unchanged, but a future ranking change could have mislabeled a
different policy as the frozen candidate. The artifact is preserved but
quarantined from forward eligibility.

PR #209 separated dynamic ranking from frozen selection. The resumable/offline
path now always retrieves `hold_shadow.CANDIDATE_ID`, passes that exact policy
map and an explicit adaptive-baseline simulation to candidate validation, emits
explicit frozen-selection fields plus backward-compatible aliases, and fails
closed if the frozen map is absent. Focused regressions prove that a different
dynamic winner cannot alter the selected candidate.

All four required exact-head gates passed on
`74ce0d63230d032fd3e8433f684aae5ad2684b5b`; PR #209 was squash-merged as
`5e7f8bdb7901985dbb4c62d38cc139eb353bda41`. Settled Splendid acceptance on
the repair commit passes: sentinel `quiet/pass`, zero incidents or collection
errors, self-check pass, daily audit 11/11, zero accounting issues, 71-row
hash-valid ledger / 25 current-v4 rows, released v4 validation, healthy runner,
market data, valuation, and risk, and no halt. V2 correctly reports `not_run`
under engine version `performance-audit-lab-v2-2026-09-09-v7-frozen-candidate-binding`.

Replacement isolated workflow `34333382201` completed successfully on main
`8636a918e7871b84f5265f13a63ef6f315e820bf`. Artifact `10096867856`, digest
`sha256:a2be1b42f79f261d2de0d6920a2a2aebaced700e90a95db5ad5337321ed56c93`,
is bound to the corrected v7 engine, loads 45/45 symbols with no provider errors,
and explicitly reports `current_full_sample_best_variant=hold_10d`,
`selected_candidate=hold_10d`, `candidate_id=hold_10d`, frozen date
`2026-09-09`, and identical selected/compatibility validation payloads. The
execution boundary confirms isolated process, no production web worker or paper
runner, no broker access, and no order authority.

The corrected forward report is clean and `collecting`: zero exact matched
completed lifecycles, zero exit divergences, zero available post-freeze sessions,
no integrity errors, all criteria not yet met, and automatic promotion false.
This is the expected initial state before the first post-freeze market session;
do not fabricate or backfill observations from pre-freeze history.

No production holding period, exit, signal, sizing, risk, state, canonical
history, broker, live, AI/ML, or order authority changed. Issue #208 is closed;
Issue #202 remains open while genuine forward observations accumulate.

## 2026-09-09 Issues #212/#214 — Runner-Liveness Observability Repair — COMPLETE

Intraday read-only checks demonstrated that compact self-check and daily audit
could trust persisted `thread_started=true` after automatic-attempt telemetry
became stale. PR #213 made both surfaces fail closed after the configured
freshness window and added them to the mandatory Change Safety regression
selection. All four exact-head gates passed; it was squash-merged as
`7eeaa3208b5297216a5f98c917bc4324aa1aa489`.

Settled validation then showed a distinct telemetry path: the canonical cycle
completion contract continued recording healthy automatic completions while the
older attempt/run fields lagged. PRs #215 and #216 made the newest causally
automatic attempt, run, success, skip, or cycle-completion timestamp the bounded
liveness evidence, while retaining the stale/no-evidence failure. Focused
regressions cover both read-only audit surfaces. Every required exact-head gate
passed on both repairs; the final merge is
`eeedc4655e780a438704b88e4ea8fea5944427e7`.

Settled Splendid acceptance on the final commit passes: sentinel `quiet/pass`
with zero incidents or collection errors; self-check `pass` with
`liveness_evidence=cycle_completion`; daily audit 11/11; a fresh completed
automatic cycle; zero accounting coverage/economic issues; 71-row hash-valid
canonical ledger / 25 current-v4 rows; released v4 validation; healthy startup,
market data, valuation, and risk; and no halt or self-defense.

The frozen `hold_10d` forward-shadow program remains research-only and unchanged.
AI review remains disabled with zero observations. No strategy, signal, ranking,
selection, sizing, exposure, stop, exit, hold period, hard-risk limit,
canonical/accounting/history, state/day-peak, broker, live, AI/ML, or order
authority changed.

## 2026-09-09 Issue #202 Stage 2 — First Forward Session Captured

After the first complete post-freeze market session, PR #218 advanced only the
isolated resumable request from verified workflow \`34333382201\`. Its exact-head
Change Safety gate passed and it was squash-merged as
\`545cb7d137adbecb357756461ace40d28fef2958\`. No duplicate research job was
active and production V2 remained disabled/not-run.

Isolated workflow \`34406640570\` completed successfully. Artifact
\`performance-audit-v2-evidence\` (\`10125603352\`), digest
\`sha256:72444be86f5199be94004819793f3fa8d972e36d047ff567b68953722e2debb7\`,
is bound to that main commit and preserves the isolated boundary: no production
web worker, paper runner, broker access, or order authority.

The frozen \`hold_10d\` report now records one available forward session
(\`2026-09-09\`), zero exact matched completed lifecycles, zero exit divergences,
and no integrity errors. This is expected before any frozen-policy lifecycle can
complete. Status remains \`collecting\`; every sample, duration, regime, pairing,
concentration, cost, and stress promotion gate remains unsatisfied, and automatic
promotion remains disabled.

Settled Splendid acceptance on the request merge passes: sentinel \`quiet/pass\`,
self-check pass, daily audit 11/11, healthy automatic after-hours skip evidence,
zero accounting issues, 71-row hash-valid canonical ledger / 25 current-v4 rows,
released v4 validation, healthy market data and risk, and no halt or self-defense.
No production trading behavior or authority changed.

## 2026-09-10 Issue #220 — Bounded OpenAI Shadow Transport — IN PROGRESS

The user reported creating a dedicated restricted OpenAI API key, adding it to
Railway as `SHADOW_AI_OPENAI_API_KEY`, and completing the resulting deployment.
The secret value was not retrieved, logged, committed, or otherwise exposed.
Key presence alone remains inert because `SHADOW_AI_ENABLED` defaults false.

Branch `feat/issue-220-openai-shadow-transport` adds a standard-library OpenAI
Responses transport fixed to `gpt-5.6-terra`, strict structured output, no
tools, `store=false`, bounded input/output, 20-second maximum timeout, two
attempts, one request per cycle, 25 requests per UTC day, $0.50 per UTC day,
and $10 per UTC month. The dollar checks reserve the maximum accepted request
cost before network access and use the restart-durable evidence store for
day/month usage. Missing or corrupt budget evidence, invalid provider/model
configuration, missing credentials, transport failures, malformed output, and
identity/schema failures all stay unavailable or disabled without blocking the
paper runner. Provider status exposes readiness and usage but never the secret.

Focused transport, reviewer, observability, runtime-ordering, and complete
shadow-AI regressions pass locally. No live request has been made and the
reviewer is not yet enabled. Before any merge or activation, inspect the exact
diff and require every exact-head repository gate. After merge, first accept the
disabled deployment on Splendid; activation is a separate bounded Railway
configuration step and remains shadow-only. Issue #202 performance evidence is
independent and unchanged.

## 2026-09-10 Issue #220 — Bounded OpenAI Shadow Transport — COMPLETE

PR #221 passed all four mandatory exact-head workflows and was squash-merged as
`6184302dc3f227014c8032268e1445346c0d5289`. Settled Splendid evidence confirms
the bounded OpenAI reviewer is enabled and healthy in shadow-only, rules-only
mode with model `gpt-5.6-terra`, no tools, no execution wait, no order authority,
and exact accepted-request cost coverage. At the 13:05 CDT audit it had 13
accepted observations, zero unavailable/fallback observations, and $0.061658 in
exact covered cost against the 25-request/$0.50 daily and $10 monthly caps. The
dedicated secret value was never retrieved or exposed.

Issue #202 remains independent: production V2 is disabled/not-run and the frozen
`hold_10d` candidate remains research-only with one forward session and zero
matched completed lifecycles or divergences.

## 2026-09-10 Issue #222 — Canonical/State Execution Divergence — ACTIVE

Intraday evidence demonstrated that the valid GEV short entry
`9cad03cbec994e29a9b65293d573f54b` (1.091006 shares at 920.93, recorded 11:25
CDT) was durably appended to the hash-valid canonical ledger and immediately
projected to state, but a later stale state replacement removed it without a
canonical exit. The immutable ledger and trade journal preserve the row. State
and its derived accounting remained one current-v4 execution behind, while the
existing ledger-chain, accounting, self-check, daily-audit, and sentinel checks
incorrectly passed. No historical file was altered or repaired.

The bounded prospective repair makes composition-guard telemetry use the
transaction manager, serializes all transactional read/modify/write work behind
the canonical cycle mutation lock, and blocks any same-epoch save or transaction
that would remove an already persisted execution ID. Canonical ledger status now
checks bidirectional current-epoch execution-ID parity, and a mismatch fails the
routine self-check and daily audit and raises a critical sentinel incident. Tests
cover stale-save rejection, append and successor-epoch compatibility,
transaction/cycle serialization, non-destructive telemetry persistence, and
audit/sentinel propagation. Historical reconciliation remains explicitly out of
scope and may occur only through a separate exact-evidence successor process
with validation hold; do not rewrite the canonical ledger or silently backfill
state.

PR #223 passed all five exact-head workflows (Change Safety including Gunicorn,
Repository Safety and Performance, Architecture Debt, System Sentinel Shadow,
and the full Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/
Research audit) on `153b1bc8d4f4222419d708eceae7f58913a08ba4` and was squash-merged as
`aa7b100355be218243feab3056a9e8a22b3af143`.

Settled Splendid acceptance correctly failed closed and exposed that the scope
is larger than the first GEV row: the 78-row hash-valid ledger has 32
current-v4 execution IDs while state has 28. Missing state IDs are the original
GEV entry plus `9554247470c54fe9a00598da6a346f46`,
`96cdc732bf6b475098a9b6887ac76fa7`, and
`c90260025d4b4eed8b3a0029e0267b5f`. Self-check is `fail` with only
`canonical_state_parity`; daily audit is `fail` with critical successor-only
next action; and sentinel reports one critical execution-projection incident.
The automatic runner is otherwise fresh, the ledger chain remains valid, and
no evidence was changed. Because diagnostics alone did not stop new paper
entries, the bounded follow-up latches and persists a risk halt during canonical
ledger startup whenever current-epoch parity is broken, without overwriting an
existing halt reason or changing any execution/history evidence. Issue #222
remains open until that halt containment is deployed and accepted.

## 2026-09-10 Issue #222 — Prospective Halt Containment — MERGED / RUNTIME ACCEPTANCE PENDING

PR #224 added the bounded fail-closed containment for the demonstrated
canonical/state execution divergence. On current main it was squash-merged at
exact head as `4889789643af6b82ec3316c171929fe01be1844e`. The repair latches and
persists a paper risk halt during canonical-ledger startup when current-epoch
canonical/state execution-ID parity is false, preserves any existing halt
reason, and does not rewrite canonical rows, state/history, accounting,
day-peak, recovery evidence, strategy, thresholds, hard-risk limits, live,
AI/ML, broker, or order authority.

All post-merge repository and deployment contexts are green: Change Safety,
Repository Safety and Performance, Architecture Debt, the full
Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research audit,
and both Railway deployment checks. These checks establish that the intended
containment is built and deployed, but they are not a substitute for the
settled authoritative runtime endpoints.

The current execution environment could not reach the authoritative Splendid
endpoint (browser returned `ERR_BLOCKED_BY_CLIENT`), so no live sentinel,
self-check, daily-audit, accounting, ledger, runner, market-data, or risk result
was inferred and no halt was cleared. Issue #222 remains open pending a fresh
authoritative post-deploy capture and any separately governed successor
reconciliation of the four already-missing current-v4 state IDs. The immutable
ledger/history evidence remains untouched.

Issue #202 and the frozen `hold_10d` forward-shadow program remain unchanged
and research-only; no performance candidate was adjusted or promoted while this
correctness containment awaits settled runtime acceptance.

## 2026-09-12 Issue #222 — Cross-Day Integrity-Halt Reset — FIX IN VALIDATION

Fresh authoritative Splendid evidence on current main `10b136ab5cf29fd0880e9c73ea337f83004de3f4`
shows the hash-valid canonical ledger at 87 rows / 41 current-v4 execution IDs
while state contains 37 current-v4 IDs. The same four execution IDs documented
above remain absent from state, so canonical/state projection parity is still
false and the ledger correctly reports that it is not authoritative for new
executions. Despite that unresolved critical condition, the current risk state
is unhalted with no self-defense active.

The demonstrated cause is lifecycle ordering, not new ledger corruption. PR
#224 latches the parity halt during canonical-ledger startup, but the ordinary
new-trading-day reset subsequently replaces the risk-control dictionary with a
fresh default and discards the parity marker, halt flag, reason, timestamp, and
missing-ID evidence. The existing prospective save/transaction guards remain
installed; the missing historical state projections are unchanged.

Branch `fix/issue-222-runtime-parity-halt` makes the fresh-day baseline guard
carry only the canonical/state projection-divergence halt and its evidence into
the new day's otherwise normal risk-metric reset. Ordinary daily-loss halts
continue to reset normally. It does not clear a halt, change thresholds,
strategy, sizing, accounting, canonical rows, state/history, recovery evidence,
live or AI/ML authority, or place orders. Focused regressions cover both legacy
`get_risk_controls` and valuation-driven `update_daily_risk_controls` reset
paths; the focused and affected invariant set passes 144 tests. Exact-head CI
and settled Splendid deployment acceptance remain required before this stage is
complete. Issue #202 remains frozen while Issue #222 is active.

## 2026-09-12 Issue #222 — Cross-Day Integrity-Halt Reset — COMPLETE

PR #226 passed all five exact-head workflows (Change Safety including exact
Gunicorn smoke, Repository Safety and Performance, Architecture Debt, Fresh Day
Compact Check, and the full Refactor/Ownership/Configuration/State/Decision/
Runtime/Startup/Research audit) on `cdcb6b05118efd539741fa936e969e5007df8636`
and was squash-merged as `18680cd26448bf60387d56aeb4d738661d090995`.
Both Railway deployment contexts and all post-merge repository contexts passed.

Settled authoritative Splendid acceptance is bound to the merge commit. Startup
is ready; the 87-row ledger remains hash-chain valid; current-v4 parity remains
correctly false at 41 canonical versus 37 state execution IDs; and the same four
missing IDs remain visible. The intended containment is now active and persisted:
paper risk is halted for `canonical execution/state projection divergence`, the
ledger is not authoritative for new executions, and sentinel reports the single
critical execution-projection incident. Accounting reconstruction remains clean
with zero coverage or economic issues, valuation is eligible, the runner has no
active error, and market-data request accounting is complete with no circuit
open. No canonical row, state/history, accounting, recovery record, threshold,
strategy, sizing, live/AI authority, or order was changed.

Issue #222 remains open for the separately governed successor reconciliation of
the four pre-existing missing state projections; the halt must not be manually
cleared. Issue #202 and all performance promotion remain frozen until parity is
resolved and post-reconciliation forward/runtime acceptance passes.

## 2026-09-12 Issue #222 — Successor Reconciliation Evidence — IN VALIDATION

The cross-day halt is now accepted, so the next bounded stage is collecting the
exact immutable signatures needed to design the four-row successor
reconciliation without guessing or exposing a state-write control. Branch
`fix/issue-222-reconciliation-evidence` adds the already-detected missing
current-epoch rows to the existing read-only canonical-ledger status, capped at
the same ten-row diagnostic boundary and limited to execution identity, chain
hashes, epoch/version, timestamp, action, symbol, side, price, and quantity.

This stage is observability only: it does not repair state, rewrite canonical
history, clear the active parity halt, call the broker, place orders, or change
strategy, sizing, thresholds, live, or AI/ML authority. After exact-head gates
and deployment acceptance, use the four exact event hashes and lifecycle fields
to define a separately tested, archival, restart-safe successor reconciliation.
Issue #202 remains frozen.


## 2026-09-14 Issue #222 evidence and Issue #229 accounting classification — IN VALIDATION

PR #228 passed all four exact-head repository workflows at
`741216d6b3840222f5d2c711728ecc7c30560fc7`, including the exact Gunicorn smoke,
and squash-merged as `97e1903c4f1e60335a751c43c37dd2f09ad16966`.
Settled authoritative Splendid acceptance is bound to that merge: startup is
ready/delegating on the exact commit; the canonical ledger remains chain-valid
with 87 rows; the active epoch remains 41 canonical rows versus 37 state rows;
and the same four missing entry projections are now exposed with their exact
immutable event hashes and lifecycle fields. The existing parity halt remains
active and persisted. No canonical, state, accounting, history, day-peak, or
recovery evidence was changed.

The same settled capture demonstrated a separate read-only classification
defect: deterministic accounting and aggregate state agree on the open ORCL
short (`13.654189` reconstructed versus `13.65` aggregate unrealized P/L), but
accounting integrity warns because the minimal canonical position row omits the
optional per-position P/L cache. Issue #229 and branch
`fix/issue-229-optional-unrealized-reporting` treat an absent cache as absent,
continue checking it when present, add an aggregate P/L comparison, and add
focused regressions. This change cannot repair state, clear the Issue #222 halt,
or change strategy, risk, sizing, execution, live, or AI/ML authority. Issue
#202 remains frozen; no duplicate research run was launched.

## 2026-09-14 Issue #229 complete and Issue #231 sentinel classification — IN VALIDATION

PR #230 passed all four exact-head workflows on
`621a00dc7d4e1008ba2a3a5647983bc8c5d8ebbc`, including Change Safety and exact
Gunicorn smoke, and squash-merged as
`f6a801af373ce5258b332d9456bbe27f1818bb1c`. Settled Splendid acceptance on that
exact deployment proves accounting integrity `ok/pass`, complete coverage, zero
discrepancies, and no automatic repair. The active ORCL short subsequently
closed through the rules-owned lifecycle; ledger/state counts advanced together
from 41/37 to 42/38 and the same four historical missing projections remain.
Issue #222's parity halt remains active and persisted; no halt or history was
cleared or rewritten.

The settled capture also demonstrated Issue #231: daily market-data accounting
can pass with the one request that its snapshot contract permits to be in
flight, but sentinel normalizes the gap to zero without normalizing the related
completeness flag, producing a contradictory high-severity incident. Branch
`fix/issue-231-sentinel-inflight-classification` makes those two sentinel-only
fields consistent while retaining the observed gap and continuing to fail on a
gap above one or a provider failure. This is read-only classification only and
does not change provider, execution, state, accounting, risk, strategy, sizing,
live, or AI/ML behavior. Issue #202 remains frozen and no research job was
launched.

## 2026-09-14 Issues #229 and #231 — COMPLETE

PR #230 passed all four exact-head workflows, including exact Gunicorn smoke,
on `621a00dc7d4e1008ba2a3a5647983bc8c5d8ebbc` and squash-merged as
`f6a801af373ce5258b332d9456bbe27f1818bb1c`. Settled Splendid acceptance proved
accounting integrity `ok/pass`, complete coverage, zero discrepancies, and no
automatic repair. PR #232 then passed the same four mandatory exact-head gates
on `31d89434ae037e272d3326519ef5c48c4f4d53ef` and squash-merged as
`0003ad17956225e05b2175e7b36f24e5d3d6d95c`.

Settled acceptance on the exact final deployment is ready/delegating. Sentinel
now reports only the genuine Issue #222 execution-projection incident; with one
provider request concurrently in flight it retains observed gap `1`, normalizes
the permitted sentinel gap to `0`, and reports snapshot completeness without a
false market-data incident. Accounting is `ok/pass` with 38 parsed state rows,
complete coverage, zero economic/coverage issues, zero discrepancies, and a
flat book. The canonical ledger is hash-chain valid at 88 rows / 42 current-epoch
rows versus 38 state rows; the exact same four historical projections remain
missing and the parity halt remains active and persisted. The runner has no
active error and provider status passes.

The rules-owned ORCL short completed a trailing-stop exit during the validation
window for `4.383375 @ 142.275`, recording execution
`a28005eb52b34e31a431b446ea68f0c7` and state/canonical counts advanced together.
No new entry was admitted through the halt. Shadow AI remains observer-only and
healthy with 91 durable integrity-valid records, 51 join-eligible results,
43.956% unavailable, exact cumulative cost `$0.238310`, and no promotion
authority. Production Performance Audit V2 remains disabled/not-run; the frozen
Issue #202 artifact remains one forward session with zero matched completed
lifecycles and zero divergences, so all promotion gates remain inconclusive.
No duplicate research job was launched and no canonical/state/history/day-peak/
recovery evidence or trading authority was changed. The next correctness action
remains a separately governed, archival, exact-signature successor
reconciliation for Issue #222; do not clear the halt manually.


## 2026-09-14 Issue #222 — Reconciliation authority boundary

Read-only forensic review confirms the four absent state projections are a
contiguous canonical-ledger entry chain: GEV event
`1504ba26dd40438328b463af2bda4eb7d5394234d8d9bf50acf37883209450ae`,
SPCX events `82d2b757418690153b38e66b9e447132666401daf0a85c932ffc0f4b3795fcf2`
and `4bfc5ba82b6dd95bbc99952dbfce446cd29336ff82759458279627768c6ae598`,
and ACHR event
`313543e183e5a7368e57fd7d7d50a7eb45f19b4db30e2d14375109199caf0949`.
Their exact entry notionals are approximately $1,004.740501,
$1,004.740497, $1,004.740497, and $1,004.740508, respectively
($4,018.962003 total). They have no matching state-projected lifecycle, while
subsequent canonical/state executions continued and the current state book is
flat.

This makes the next step an economically material successor-state decision,
not a routine observability fix: blindly replaying the four entries would
resurrect three short symbols/four lots and reserve roughly $4,019 of capital;
ignoring their later lifecycle would also leave the successor accounting open.
The existing Issue #172 recovery is intentionally unusable for this shape and,
when its exact preflight matches, auto-applies from the startup bridge. Therefore
no Issue #222 recovery module may be registered or allowed to auto-apply until a
separately authorized disposition defines the exact successor economics and
exit treatment. The active parity halt remains the correct fail-closed state.
No canonical row, state/history, accounting, day peak, recovery artifact, risk
control, order, or authority was changed. Issue #202 remains frozen and no
research job was launched.


PR #234 exact head `2249662bcd90da86d75aa6c17c58c66e1d0cab07` passed its docs-only exact-head Change Safety workflow and was squash-merged as `409a28d2ae130867bc211ca684184e619ce97bc3`. This merge changes documentation only; authoritative runtime behavior and the active Issue #222 halt are unchanged.


## 2026-09-14 Issue #222 — Authorized verified-flat successor — IN VALIDATION

The user explicitly authorized a non-destructive successor after independent
read-only evidence was exhausted. The four exact missing short entries form a
contiguous immutable chain, but no exact later GEV/SPCX/ACHR exit or partial-exit
evidence is present; the accepted current state and independent accounting
reconstruction are flat. No exit will be inferred or fabricated.

Branch `fix/issue-222-verified-flat-successor` adds an exact-shape, paper-only
v4-to-v5 migration. It requires the 88-row hash-valid ledger, 42 v4 rows versus
38 state rows, the exact four missing IDs and immutable entry signatures, their
contiguous hash linkage, the exact ORCL tail, no later candidate exit for the
three affected symbols, clean flat accounting, the exact flat cash/equity
snapshot, released v4 lineage, and the active projection-divergence halt. Any
drift blocks without a state write.

On an exact match only, it archives the full prior persistence and immutable
ledger digest, begins
`stable-paper-v5-20260914-issue222-flat-successor01` from the verified flat
cash/equity baseline, clears only the new epoch's active trade window, marks the
v4 discrepancy unresolved and permanently non-promotable, records zero
fabricated exits, and applies a validation hold. Risk controls, day peak,
history, canonical ledger, strategy, sizing, hard-risk limits, live authority,
AI/ML authority, and order authority remain unchanged; the existing parity halt
is preserved. Restart, concurrent-apply, signature drift, later-exit candidate,
non-flat/accounting, marker, lineage compatibility, and v4-release supersession
regressions are included.

No successor has been deployed or applied yet. Exact diff inspection, every
mandatory exact-head gate including exact Gunicorn startup, and settled
authoritative Splendid acceptance are required before completion. Issue #202
remains frozen and no research job was launched.


## 2026-09-14 Issue #222 — merged; settled runtime evidence pending

PR #236 exact head `7150650ae42f1cb4e9e0f6cac2a39767f0459b07` passed all four mandatory exact-head workflows: repository safety/performance, architecture-debt regression, Change Safety, and the full refactor/ownership/configuration/state/decision/runtime/startup/research audit. The full audit included the focused successor/restart/concurrency regressions and exact Gunicorn startup smoke. Exact-diff inspection remained bounded to the Issue #222 successor, startup and lineage compatibility, v4-release supersession, focused tests, classification, and this handoff. The initial architecture duplicate-owner finding was corrected by reusing the established successor primitives and the corrected exact head passed.

The PR squash-merged to main as `beef6e24a548efafe7d1edfe7ae866b9b9e546f1`. The authoritative `splendid-creativity / web` deployment context reached success, as did post-merge repository validation and daily operational audit. The unrelated legacy Railway context is not authoritative and was not used.

This run could not obtain a read-only response from the authoritative runtime URL because the available network reader rejected the Railway domain before making a request. Therefore neither successor application nor the v5 settled invariants are inferred from deployment status: settled runtime acceptance remains open. Do not manually clear the parity halt. The required next probe must confirm the exact v5 epoch and completed marker, validation hold active, prior discrepancy unresolved/non-promotable, zero fabricated exits, flat positions/trades, unchanged cash/equity/risk/day peak/history and canonical-ledger digest, clean accounting, and restart stability. If exact preconditions did not match, preserve the blocked v4 state and diagnose without mutation.

Issue #202 remains frozen and no research job was launched. Issue #84 does not begin until Issue #222 receives settled authoritative acceptance.


## 2026-09-15 Issue #222 — verified-flat successor settled acceptance — COMPLETE

Read-only independent evidence was exhausted before cutover. The only later
affected-symbol exit is the exact complete, separately bound ACHR lifecycle
(`acaa0e0eda6b4eb4a26597f2f1acdec3` entry to
`10d56e9128cc4afe896df89b01df137c` exit); it does not close any of the four
missing entry lifecycles. Exact exits for the missing GEV, two SPCX, and ACHR
entries remain unavailable, so their v4 discrepancy is retained as unresolved
and permanently non-promotable. No exit was inferred or fabricated.

PR #242 completed the exact later-pair binding and corrected the focused
successor fixture so restart/concurrency/signature regressions genuinely run.
It passed all four exact-head gates, including exact Gunicorn smoke, and merged
as `b5103855b1cadbefc9966dcd840d0e09cf56289f`. Settled Splendid then applied the
authorized successor exactly once. The forensic archive is
`/app/data/forensic_archives/20260915_132337_607645_issue-222-unresolved-v4-entry-projection-flat-successor-2026-09-14`;
the canonical ledger remained byte-for-byte unchanged.

PRs #243 and #244 made the exact verified-flat, zero-current-trade baseline
complete accounting evidence in both the legacy guard and the active
bidirectional runtime owner. PR #245 added bounded startup failing-module
diagnostics after the first post-merge container failed closed. That diagnostic
identified the durable legacy v2-to-v3 completion marker as the remaining
startup blocker. PR #246 extended the existing read-only compatibility owner to
treat only the exact archived v5 lineage as superseding that legacy migration.
Every PR passed all mandatory exact-head workflows; Change Safety and the full
audit included exact Gunicorn startup smoke. Final main is
`a605e7b1751263bf1f1b8fbd2cce6aa5a28e52be`, and its post-merge repository,
architecture, Change Safety, full audit, and authoritative Splendid deployment
contexts passed.

Settled authoritative Splendid evidence on 2026-09-15 is ready/delegating on
that exact commit. The successor reports `validation_hold/pass`, epoch
`stable-paper-v5-20260914-issue222-flat-successor01`, cash
`13429.13048559457`, equity `13429.13`, no positions, no current-epoch state
trades, zero fabricated exits, archived historical evidence, and the v4
economics non-promotable. The canonical ledger is hash-chain valid at 88
immutable rows with v5 canonical/state counts 0/0, full parity, and zero missing
IDs. Accounting is `ok/pass`, complete, zero discrepancies, no repair, and
reports the exact verified-flat baseline with unrealized P/L 0. Sentinel is
quiet/pass with zero incidents; the automatic runner completed normally;
market-data/path integrity passes. The daily audit's only failure is the
intentionally preserved administrative parity halt, not an accounting,
canonical, runner, or market-data defect. The halt was not manually cleared.

Rollback/recovery evidence is the immutable archived v4 state plus its manifest,
the durable one-time v5 marker, and the unchanged canonical ledger digest. No
rollback was performed because settled v5 acceptance passed. Any future lineage,
snapshot, flatness, archive, zero-fabrication, or halt drift remains fail-closed.

Issue #202 remains frozen: Performance Audit V2, ablation, and regime work are
disabled/not run, and no promotion authority changed. Shadow AI remains
observer-only; its evidence is durable but unavailable concentration remains too
high for promotion. Issue #84 is now the primary engineering program: implement
the authoritative single-owner StateStore/ledger-projection/valuation/risk
cutover before any performance or AI promotion work.


## 2026-09-15 Issue #84 — Stage D envelope deep-immutability foundation — COMPLETE

The first bounded Issue #84 cutover-readiness review confirmed that Stable Paper
Core v3 Stages B-F remain shadow-only and are not registered with the production
runtime. It also demonstrated a concrete StateStore integrity defect: a prepared
`CanonicalStateEnvelope` froze only its top-level payload mapping. Nested
portfolio, position, risk, and epoch mappings/lists remained mutable after the
payload digest was validated. A caller could therefore change canonical
economics in memory while retaining the old digest; `snapshot()` consumed those
changed values, and a later sandbox commit could replace the file before
post-commit readback detected the stale digest.

PR #248 recursively detaches and freezes the complete envelope payload and
converts it back to a detached plain graph only at snapshot/serialization
boundaries. Focused regressions prove that nested portfolio and position
mutation fails, a mutated exported plain copy cannot affect the envelope, and
digest/restart/backup/revision behavior remains unchanged. The exact PR head
`a898fe2d3b9afb7f579df03121a8a8ad9a66fa9f` passed all five applicable
workflows: Stage D validation, repository validation, architecture-debt
regression, the full refactor/ownership/runtime/startup audit, and mandatory
Change Safety. Change Safety's exact Gunicorn bootstrap smoke passed. The PR
squash-merged as `dbdbec211d1b91e20dbf2356d5a5833fa2ffab86`; its post-merge
checks and authoritative `splendid-creativity / web` deployment passed.

Settled read-only Splendid acceptance is bound to that exact merge commit:
sentinel is `pass` with zero incidents; self-check reports canonical parity and
accounting pass; the append-only ledger remains chain-valid at 88 immutable rows
with v5 canonical/state counts 0/0 and no missing IDs; accounting remains
complete with zero discrepancies, zero repairs, and zero fabricated exits; cash
is `13429.13048559457`, equity is `13429.13`, positions are empty, and realized
today/unrealized P&L are both zero. The automatic runner remains active and
continues to block entries on the intentionally preserved parity halt. The daily
audit's only failure is that administrative halt. No production state, ledger,
history, day baseline/peak, risk threshold, strategy, order authority, or AI/ML
authority changed, and `/paper/run` was not called.

Rollback is a code-only revert of PR #248; no data rollback or recovery action
is required because the repaired interface remains shadow-only and made no
production writes. Issue #84 remains open. Before an authoritative cutover,
prove cross-instance/process StateStore serialization and single-writer
ownership, bind the existing ledger projector, protected valuation, and risk
evaluation to one immutable snapshot revision, and complete the explicit Stage
F cutover/rollback review. Do not enable production StateStore writes merely to
produce parity evidence. Issue #202 remains frozen and no performance or AI
promotion work resumed.


## 2026-09-15 Issue #84 — cross-process StateStore serialization — COMPLETE

The next bounded Stage D review demonstrated that the shadow StateStore's
instance-local `RLock` did not satisfy the single-writer transaction boundary.
Two independent processes could both read revision N, accept the same N+1
envelope, and overwrite one another. Atomic replacement protected file shape,
but it did not make the monotonic compare/backup/write/readback sequence atomic
across worker processes.

PR #250 adds a deterministic same-directory advisory lock. Sandbox reads take a
shared lock; commits take an exclusive lock across revision comparison, prior
revision backup, atomic replacement, fsync, and post-commit readback. The Stage
D contract and descriptor now require cross-instance/process serialization. A
deterministic two-process regression pauses one writer after it reads revision
1, proves a second writer cannot pass the held process lock, then proves that
the second writer rejects duplicate revision 2 after the first commits. Existing
deep immutability, digest, backup, restart, revision, and Stage B-F invariants
remain green.

The exact PR head `6de5c9d9a47811859796b9dc6410af67dcf015b7` passed all five
applicable workflows: Stage D validation, repository validation,
architecture-debt regression, the full refactor/ownership/runtime/startup audit,
and mandatory Change Safety. The exact Gunicorn bootstrap smoke passed. The PR
squash-merged as `848c8d46ca202ee243bee2c3c929113f172adb83`; all post-merge
checks and the authoritative `splendid-creativity / web` deployment passed.

Settled read-only Splendid acceptance is bound to that exact merge: sentinel is
quiet/pass with zero incidents; self-check has no failing components; the
automatic runner completed its last eligible market cycle normally and now
skips after the regular session. Canonical/accounting evidence remains unchanged
and clean: the ledger is chain-valid at 88 immutable rows, v5 canonical/state
counts are 0/0 with full parity and no missing IDs, accounting is complete with
zero discrepancies/repairs/fabricated exits, cash is `13429.13048559457`, equity
is `13429.13`, positions and recent trades are empty, and realized-today and
unrealized P/L are both zero. The intentionally preserved parity halt remains;
the daily audit fails only that risk section. `/paper/run` was not called.

The repair remains shadow-only, explicit-sandbox opt-in, production-write
disabled, and runtime-unregistered. It changed no production state, canonical
ledger, history, recovery evidence, day baseline/peak, risk limit, policy,
orders, or AI/ML authority. Rollback is a code-only revert of PR #250; no data
recovery is needed. Issue #84 remains open. Next, prove one immutable snapshot
revision can bind the canonical ledger projection, protected valuation, and risk
evaluation with exact parity and an armed rollback plan before considering any
authoritative writer activation. Issue #202 remains frozen; V2, ablation, and
regime work remain disabled/not run, and no duplicate research job was started.


## 2026-09-15 Issue #84 — single-revision cutover parity proof — COMPLETE

The next Stage F review found that future-canary readiness could be represented
by independent parity booleans without proving that StateStore, canonical-ledger
projection, protected valuation, and risk evaluation described the same
immutable revision. That allowed logically stale or mixed-snapshot evidence to
appear complete even though each subsystem passed separately.

PR #252 adds a shadow-only immutable `SnapshotBindingProof` to the existing
canary readiness owner. The verifier requires a positive StateStore revision,
valid canonical chain, exact projected ledger-row count, full accounting
portfolio equality, exact protected-valuation cash/equity/unrealized/position
equality, exact risk-state equality, and the valuation-version lineage consumed
by risk. The proof requires rollback to remain armed and cannot hold runtime,
state-write, risk-mutation, or order authority. Stage F readiness now has an
explicit single-revision binding requirement. Regressions prove a complete
entry/projector/valuation/risk/envelope chain and fail closed on ledger-row
drift.

The exact PR head `35ee61e9b1b8138ff0ed8cde29043ebe2c949443` passed Stage F
validation, repository validation, architecture-debt regression, the full
refactor/ownership/runtime/startup audit, and mandatory Change Safety. The exact
Gunicorn bootstrap smoke passed. The PR squash-merged as
`ef17261d0b79aea9c4a8b4df5a23446402051c2d`; post-merge checks and the
authoritative `splendid-creativity / web` deployment passed.

Settled read-only Splendid acceptance is bound to that exact merge: bootstrap
is ready/delegating, sentinel is quiet/pass with zero incidents, self-check has
no failing components, and the runner is healthy and correctly skipping after
the session. Canonical/accounting evidence remains unchanged: 88 immutable
chain-valid rows, v5 canonical/state counts 0/0, full parity, no missing IDs,
complete accounting with zero discrepancies/repairs/fabricated exits, cash
`13429.13048559457`, equity `13429.13`, no positions or recent trades, and zero
realized-today/unrealized P/L. The intentionally preserved parity halt remains;
the daily audit fails only that risk section. `/paper/run` was not called.

This remains a pure shadow proof and did not activate runtime or production
writes. No state, ledger, history, recovery, day baseline/peak, threshold,
strategy, risk, order, or AI/ML authority changed. Rollback is a code-only
revert of PR #252. Issue #84 remains open. Next, build the bounded read-only
adapter that derives this typed proof from current authoritative v5 evidence;
require exact epoch/row/digest provenance and keep any mismatch non-promotable
before considering writer activation. Issue #202 stays frozen; V2, ablation,
and regime remain disabled/not run, with no duplicate research job.


## 2026-09-16 Issue #84 — total versus active-epoch ledger provenance — MERGED; settled endpoint acceptance pending

The bounded adapter-readiness review demonstrated a scope error in the Stage F
single-revision proof. `CanonicalStateSnapshot.execution_ledger_rows` represented
the immutable all-epoch ledger total, while
`AccountingProjection.execution_rows` represented the active epoch projection.
The proof compared those unlike counts directly. The current v5 baseline is the
decisive regression shape: 88 preserved canonical rows in total and zero rows
in the active verified-flat successor epoch. A correct baseline could therefore
never satisfy the prior proof.

PR #254 adds explicit `execution_epoch_rows` provenance while retaining
`execution_ledger_rows` as the all-epoch total. State snapshots now require
nonnegative counts with active-epoch rows no greater than total rows; older
Stage D envelopes remain compatible by defaulting the absent epoch count to the
stored total. Stage F separately proves total/epoch ordering and compares only
active-epoch rows to the accounting projection. Stage D/F contracts and
round-trip tests were updated, and a v5-shaped 88-total/0-epoch/zero-trade
regression proves the valid successor baseline.

Local exact focused validation passed both JSON contracts and all 74 Stage
B/C/D/E/F tests. The PR exact head
`dc779cf32916fcdabc5ea54a57ac6ab47c944d4e` passed all eight applicable
exact-head workflows, including Stage C/D/E/F validation, repository safety,
architecture-debt regression, the full refactor/ownership/runtime/startup
audit, Change Safety, and exact Gunicorn bootstrap smoke. Exact-diff inspection
was bounded to seven architecture/contract/test files. PR #254 squash-merged as
`a300e25982aff64a1c3a6682e2c965e597ad74ad`; post-merge repository validation,
Change Safety, refactor audit, and the authoritative `splendid-creativity / web`
deployment context all passed.

Settled endpoint acceptance is not claimed. The available direct read-only
runtime reader rejected the authoritative Railway domain before issuing a
request. The post-deploy GitHub research snapshot completed but classified the
runtime `warn`, reported self-check unavailable, and reached only 2 of 11
research endpoints; that incomplete snapshot is inconclusive under
`VALIDATION_POLICY.md` and cannot establish current canonical/accounting/risk
invariants. The last accepted v5 evidence remains preserved but is not relabeled
as fresh acceptance for this merge. A later run must obtain a complete settled
Splendid read-only snapshot bound to `a300e259...` before advancing the adapter
or any cutover decision.

The change remains shadow-only and runtime-unregistered. It changed no
production state, ledger, history, recovery evidence, day baseline/peak, risk
limit, strategy, order authority, or AI/ML authority. Rollback is a code-only
revert of PR #254; no data recovery is required. Issue #202 remains frozen and
no research job was launched. Issue #84 remains primary; next action is to
recover complete settled read-only evidence, then implement the bounded v5
adapter with exact epoch, row-count, and digest provenance and fail-closed
non-promotable handling.


## 2026-09-16 Issue #84 — authoritative v5 evidence adapter and accounting status contract — COMPLETE

The incomplete post-PR #254 snapshot was safely retried only after the
authoritative Splendid deployment had settled. The fresh 09:02 CDT capture
reached all 11/11 endpoints and closed #254 acceptance: canonical chain valid at
88 immutable rows with v5 canonical/state counts 0/0, full parity, no missing
IDs, complete accounting with zero coverage/economic issues, flat positions,
cash `13429.13048559457`, equity `13429.13`, fresh-day baseline/peak
`13429.13048559457`, and healthy runner. The preserved parity halt and
validation hold remained active. This also demonstrated a legitimate
`0.00048559457` cash/equity difference from persisted cent serialization.

PR #256 added an exact SHA-256 digest of the canonical execution-row snapshot,
propagated it through the compact daily audit, bounded Stage B valuation to a
maximum half-cent persisted-money serialization tolerance, and added a narrow
shadow-only v5 runtime evidence adapter. The adapter fails closed unless the
authoritative Splendid source proves the exact v5 epoch, archived zero-trade
validation-held baseline, 88 total/0 active-epoch rows, valid chain, full state
parity, clean accounting, flat positions, cross-endpoint cash/equity/fresh-day/
risk consistency, positive revision, preserved parity halt, and an independently
supplied exact ledger digest. It has no runtime registration, production state
writes, order authority, risk authority, or promotion authority.

The PR exact head `98a0320f38e3b0db4cab8c836e2f5770ca73d4ea`
passed all six applicable exact-head workflows, including Stage C/F validation,
repository safety, architecture-debt regression, the full refactor/runtime/
startup audit, mandatory Change Safety, and exact Gunicorn startup smoke. The
focused Stage B-F suites passed 77 tests. PR #256 squash-merged as
`60e1e4f81d98d0200ca81066b9c49a221469232d`; authoritative
`splendid-creativity / web` deployment succeeded.

Settled acceptance then exposed a separate bounded observability defect:
`paper_accounting_readonly_status` replaced the complete accounting guard
payload and omitted the successor read-only and remaining-discrepancy fields
required by the daily operational audit. PR #257 preserved the observational,
zero-write shim while restoring those contract fields and added an exact v5
regression. Its exact head
`73f2ef0e5c290090d70c919d5e7695f656ff01ad` passed all four applicable
exact-head workflows and exact Gunicorn smoke; focused validation passed 14
tests. It squash-merged as
`27e0982453c6a486cfb32c35f79c311a6bbf3951`; authoritative Splendid
deployment succeeded. The settled daily operational audit rerun then passed
every step. Its artifact proves accounting `ok/pass`, coverage complete, no
repair, successor read-only true, automatic repair suppression false, and zero
remaining discrepancies.

The same settled artifact proves the canonical digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`,
88 rows, v5 epoch rows 0, state rows 0, valid chain, full parity, and zero
missing IDs. The 09:33 CDT research snapshot reached 11/11 endpoints: accounting
remains clean, market data and runner pass, cash/equity and the fresh-day
baseline/peak are unchanged, and the daily audit fails only the intentionally
preserved parity halt. Shadow capture is parity-pass but forward-ineligible at
1,207 cycles and 30,680 candidates. Performance Audit V1 remains enabled with
automatic backtest disabled and 1,200 forward rows; V2, ablation, and regime
remain disabled/not run. The legacy verified-v2 gate is correctly
non-applicable to active v5 and grants no authority.

The daily-audit workflow path filter omitted the read-only shim and its focused
successor test, so the accepted reporting fix would not automatically trigger
that deployment audit. The follow-up documentation/CI PR adds both paths; no
runtime behavior changes. Rollback for PRs #256/#257 is code-only; no data
rollback is required because neither change wrote production state. No ledger,
state, history, day baseline/peak, recovery evidence, thresholds, strategy,
orders, live authority, or AI/ML authority changed, and `/paper/run` was not
called. Issue #84 remains primary. Next, use the accepted typed v5 binding to
design the explicit single-owner cutover/rollback boundary without activating
production writes. Issue #202 remains frozen and no promotion work resumes.


## 2026-09-16 Issue #84 — sentinel and ledger-digest runtime acceptance coverage — COMPLETE

The automated runtime-research snapshot captured self-check, accounting,
canonical ledger counts, risk, runner, market data, Performance Audit V1/V2,
ablation, regime, and the legacy recovery diagnostic, but it did not request the
registered read-only system sentinel. It also retained the compact daily audit's
new canonical ledger digest only in raw evidence rather than the summarized
acceptance record. This was a demonstrated Issue #84 evidence-integrity gap: a
configured `11/11` result could not prove sentinel health or bind the exact
ledger bytes used by the v5 adapter.

PR #259 added `/paper/system-sentinel-status` as a required GET-only endpoint,
summarized sentinel overall/status/incidents/collection errors/deployed commit
and advisory/read-only authority, made any sentinel incident fail closed to
snapshot `warn`, and propagated the canonical ledger SHA-256 into both JSON and
Markdown summaries. It starts no worker or research, calls no cycle route,
writes no state, clears no halt, and grants no strategy, sizing, risk, order,
live, or AI/ML authority. Focused local validation passed 23 runtime-snapshot
and sentinel tests, compilation, and diff checks.

The exact PR head `87d601434b76d342fbe512d02c955da47b0a3a3b`
passed repository safety/performance, architecture-debt regression, the full
refactor/ownership/runtime/startup/research audit, mandatory Change Safety, and
exact Gunicorn startup smoke. Exact-diff inspection was limited to the collector
and its regression file. PR #259 squash-merged as
`1dab8a8b18f3f433da36082d407d9bf5aaae36ba`; all post-merge gates and
the authoritative `splendid-creativity / web` deployment succeeded.

The first post-deploy snapshot ran while deferred registration was still active
and reached only 2/12 endpoints, so it was rejected as incomplete. A safe retry
of that completed job after the deployment settled produced the accepted
13:14 CDT artifact: 12/12 endpoints reachable; bootstrap ready/delegating; the
sentinel is `pass/quiet` with zero incidents, zero collection errors,
advisory-only/read-only authority, and deployed commit exactly
`1dab8a8b18f3f433da36082d407d9bf5aaae36ba`. The canonical ledger remains
chain-valid at 88 rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
accounting is clean with zero coverage/economic issues; cash
`13429.13048559457`, equity `13429.13`, positions empty, day start/peak
unchanged, market data and runner pass, and the intentionally preserved parity
halt/validation hold remain active. Shadow capture remains parity-pass but
forward-ineligible at 1,238 cycles and 31,688 candidates. V1 remains enabled
with automatic backtesting disabled and 1,200 forward rows; V2, ablation, and
regime remain disabled/not run. No promotion authority changed.

Rollback is a code-only revert of PR #259; no data recovery is required. Issue
#84 remains primary. Next, design the explicit single-owner cutover and rollback
state machine using the accepted v5 typed binding, while keeping production
writes and runtime registration disabled until a separately reviewed cutover
decision. Issue #202 remains frozen.


## 2026-09-19 Issue #84 — cutover/rollback readiness state machine — COMPLETE

The accepted v5 typed binding proved one immutable StateStore/accounting/
valuation/risk snapshot, but Stage F still lacked an explicit transition
boundary between technical parity, rollback readiness, human-reviewed cutover,
and future writer activation. The planner descriptor also lacked its classmethod
binding and therefore was not callable on the planner class. This was bounded
offline architecture work; no market observation was manufactured and no
weekend time was counted as a forward session.

PR #261 adds immutable rollback-readiness evidence bound to the exact StateStore
revision, payload digest, and canonical-ledger digest. Readiness additionally
requires an archived baseline, successful restore drill, restart parity,
single-writer exclusivity, and a rollback switch armed by default. Its
fail-closed transition can advance only to `review_required`; it cannot activate
or roll back a writer. The current verified-flat v5 binding remains explicitly
`blocked` while its validation hold and retained parity halt are active. A
separate observational classifier identifies canonical-chain, state-projection,
accounting, valuation, risk, restart, and writer-ownership rollback triggers
without performing any mutation. The planner descriptor is now a callable
classmethod and exposes the unchanged no-authority boundary.

Focused local validation passed 82 Stage B-F and successor-boundary tests,
compilation, and exact-diff checks. Repository/Railway validation, structural
audit, ownership validation, typed-configuration parity, and architecture-debt
regression all passed locally with zero new critical or warning findings. The
exact PR head `a3cb7894f2cccece4203e061a7d6c056b1594465` passed all five
applicable exact-head workflows: Stage F, repository safety, architecture debt,
the full refactor/ownership/runtime/startup/research audit, and mandatory Change
Safety with exact Gunicorn smoke. Exact-diff inspection was limited to the Stage
F planner, contract, and focused regression file. PR #261 squash-merged as
`d74dede0a82af7b2568531acaa93325bfaf37e33`; all post-merge gates and
the authoritative `splendid-creativity / web` deployment passed.

The first automatic read-only research snapshot captured deferred registration
and reached only 2/12 endpoints, so it was rejected as incomplete. A safe rerun
after deployment settled produced the accepted 10:15 CDT artifact: 12/12
endpoints reachable; bootstrap ready/delegating; sentinel `pass/quiet`, zero
incidents and collection errors, advisory/read-only, and deployed commit exactly
`d74dede0a82af7b2568531acaa93325bfaf37e33`. The canonical ledger remains
chain-valid at 88 immutable rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
v5 accounting is clean with zero coverage/economic issues; cash is
`13429.13048559457`, equity `13429.13`, and positions are empty. Fresh-day
baseline/peak remain `13429.13048559457`; market data and runner pass. The
retained parity halt and validation hold remain active, so self-check is warn
and daily audit fails only risk exactly as intended.

Shadow capture remains parity-pass but forward-ineligible at 1,397 cycles and
36,210 candidates. Performance Audit V1 remains enabled with automatic
backtesting disabled and 1,200 forward rows; V2, ablation, and regime remain
disabled/not run. The legacy v2 recovery gate remains correctly superseded and
grants no authority. `/paper/run` was not called and no duplicate research job
was launched; the incomplete automatic snapshot was retried only after it
finished.

Rollback for PR #261 is code-only; no data recovery is required. No production
state, canonical ledger, history, day baseline/peak, recovery evidence, strategy,
sizing, hard-risk limit, order path, live authority, or AI/ML authority changed.
Issue #84 remains primary. Next, prove the rollback archive/restore drill and
single-writer handoff deterministically in an explicit sandbox while keeping the
current v5 hold/halt and all production writer registration unchanged. Issue
#202 remains frozen.


## 2026-09-19 Issue #84 — deterministic sandbox rollback and writer handoff — COMPLETE

PR #263 adds the missing executable rollback proof to the shadow-only Stage D
StateStore. An explicit caller-provided sandbox state can now be archived once
without overwrite, advanced to a canary revision, and restored from the archive
only as a new monotonic revision. Restore preserves the displaced canary bytes
in the existing prewrite backup, verifies the archived and restored payload
digests, requires an exact expected-current revision, survives restart with
identical canonical economics, and shares the same exclusive advisory process
lock as ordinary commits. A concurrent competing writer blocks behind restore
and then fails closed on the consumed revision. Default production I/O denial,
`production_write_enabled=false`, and `runtime_registered=false` are unchanged.

Focused validation passed all 14 Stage D regressions, including archive
immutability, stale-revision rejection without mutation, backup lineage,
restart parity, production-default denial, and the two-process writer-handoff
test. Compilation, repository validation, structural audit, exact-diff checks,
and architecture-debt comparison passed with zero new critical or warning
findings. The exact PR head
`e6f3eb6467b232f8fdacd5a225b552b97d559410` passed all five applicable
exact-head workflows: Stage D, repository safety, architecture debt, the full
refactor/ownership/runtime/startup/research audit, and mandatory Change Safety
with exact Gunicorn smoke. Exact-diff inspection was limited to the StateStore,
its Stage D contract, and focused regression file. PR #263 squash-merged as
`937b993eb108ae837e0fdde387140282cc14b354`; every post-merge gate passed.

The first automatic post-merge research snapshot reached only 2/12 endpoints
during deferred registration and was rejected as incomplete. A safe rerun after
the authoritative Splendid service settled reached 12/12 and proved the exact
deployed commit `937b993eb108ae837e0fdde387140282cc14b354` through the
read-only sentinel. Sentinel remains `pass/quiet` with zero incidents and
collection errors. The canonical ledger remains chain-valid at 88 immutable
rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
accounting is `ok`, cash is `13429.13048559457`, equity is `13429.13`, and
positions are empty. Day start/peak remain `13429.13048559457`; market data and
runner pass. The retained parity halt and v5 validation hold remain active, so
self-check stays warn exactly as intended. Shadow capture remains parity-pass
but forward-ineligible at 1,397 cycles and 36,210 candidates. V1 remains
enabled with automatic backtesting disabled and 1,200 forward rows; V2,
ablation, and regime remain disabled/not run.

This was an isolated temporary-directory drill only. It did not touch
production state, canonical ledger, history, day baseline/peak, or recovery
evidence; it registered no production writer, cleared no halt, changed no
strategy/sizing/risk/order/live/AI authority, launched no research job, and did
not call `/paper/run`. Rollback for PR #263 is code-only. Issue #202 remains
frozen. Issue #84 remains primary. Next, bind the successful typed Stage D drill
receipt into the Stage F rollback-readiness evidence and define the separately
reviewed, fail-closed cutover preflight without activating or registering a
production writer.


## 2026-09-20 Issue #84 — typed rollback receipt bound to Stage F — COMPLETE

PR #265 closes the evidence gap between the complete Stage D sandbox rollback
drill and Stage F cutover readiness. `CanonicalStateStore` now emits a frozen,
validated `RollbackDrillReceipt` only after one exclusive-lock sequence archives
the baseline, commits a distinct next-revision canary, restores the archived
payload as a new monotonic revision, preserves the displaced canary in the
prewrite backup, proves archive immutability, and passes restart parity. Receipt
validation fails closed on revision, digest, archive/backup lineage, incomplete
proof, runtime registration, production writes, or non-shadow authority.
Stage F can derive rollback readiness only from this typed receipt; untyped
claims are rejected. The retained v5 validation hold and parity halt remain the
only cutover blockers.

Focused validation passed 89 Stage B-F and successor-compatibility regressions,
including a two-process proof that a competing writer remains blocked across
the complete archive/canary/restore drill and then rejects the consumed
revision. Compilation, repository validation, structural/refactor audit,
exact-diff checks, and architecture-debt comparison passed with zero new
findings. The exact PR head
`9a159833a0bb1960a9c51bbd9881e82c9535ca71` passed all six applicable
exact-head workflows: Stage D, Stage F, repository safety, architecture debt,
the full refactor/ownership/runtime/startup/research audit, and mandatory
Change Safety with exact Gunicorn smoke. Exact-diff inspection was limited to
the Stage D/F implementation, contracts, focused regressions, and Stage F path
ownership. PR #265 squash-merged as
`a31896b223d5e026ab8751897910c8807ee4f621`; all post-merge gates and the
authoritative Splendid deployment passed.

The automatic post-merge snapshot was rejected as incomplete at 2/12 endpoints
while the application was still registering runtime workers. A safe read-only
rerun after deployment settled reached 12/12 and proved the exact deployed
commit `a31896b223d5e026ab8751897910c8807ee4f621`. Sentinel is
`pass/quiet` with zero incidents and collection errors. The canonical ledger
remains chain-valid at 88 immutable rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
accounting is `ok`, cash is `13429.13048559457`, equity is `13429.13`,
and positions are empty. Day start/peak remain `13429.13048559457`; market
data and runner pass. The retained parity halt and validation hold remain
active, so self-check remains warn by design. Shadow capture remains parity-pass
and forward-ineligible at 1,402 cycles and 36,210 candidates. V1 remains
enabled with automatic backtesting disabled and 1,200 forward rows; V2,
ablation, and regime remain disabled/not run.

The receipt was produced only in temporary test sandboxes. No production
StateStore writer was registered or activated; no canonical/accounting/state/
history/day-peak/recovery evidence changed; no halt was cleared; no strategy,
sizing, risk, order, live, or AI authority changed; no research job was
launched; and `/paper/run` was not called. Rollback for PR #265 is code-only.
Issue #202 remains frozen and Issue #84 remains primary. Next, define an
immutable, read-only cutover preflight decision package bound to the exact
StateStore projection, typed rollback receipt, deployed commit, and retained
hold/halt, while continuing to prohibit production writer registration or
activation absent a separately reviewed cutover decision.


## 2026-09-21 Issue #84 — immutable cutover preflight package — COMPLETE

PR #267 adds a frozen, deterministic, read-only cutover-preflight decision
package to Stage F. The package binds one verified runtime projection, the exact
typed Stage D rollback receipt and its complete archive/canary/restore/backup
lineage, the ledger and payload digests, accounting epoch, evidence source and
capture time, requested canary fraction, exact deployed and sentinel commit
SHAs, settled Splendid status, and the retained validation hold/risk halt into
one SHA-256-addressed artifact. It recomputes readiness and rollback evidence
instead of trusting caller claims, rejects malformed commit provenance and
package-digest tampering, and adds explicit fail-closed blockers for an
unsettled deployment or deployed/sentinel commit drift.

Focused validation passed 42 Stage F regressions and 91 combined Stage B-F plus
successor-compatibility regressions. Compilation, repository validation,
structural/refactor audit, architecture ownership, typed configuration,
architecture-debt comparison, and exact-diff checks all passed with zero new
findings. The exact PR head
`961608263654fe08cf942a1443db1506ef83be25` passed all five applicable
exact-head workflows: Stage F, repository safety, architecture debt, the full
refactor/ownership/runtime/startup/research audit, and mandatory Change Safety
with exact Gunicorn smoke. Exact-diff inspection was limited to the Stage F
planner, contract, and focused regressions. PR #267 squash-merged as
`2eeb3d60101f7299853925700972a5525f0ae7d9`; every post-merge gate and
the authoritative Splendid deployment passed.

The first automatic post-merge runtime snapshot reached only 2/12 endpoints
during worker registration and was rejected as incomplete. A safe read-only
rerun after deployment settled reached 12/12 and proved the exact deployed
commit `2eeb3d60101f7299853925700972a5525f0ae7d9`. Sentinel remains
`pass/quiet` with zero incidents and collection errors. The canonical ledger
remains chain-valid at 88 immutable rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
accounting is `ok`, cash is `13429.13048559457`, equity is `13429.13`,
and positions are empty. Day start/peak remain `13429.13048559457`; market
data and runner pass. The parity halt and validation hold remain active, so
self-check remains warn by design. Shadow capture remains parity-pass and
forward-ineligible at 1,412 cycles and 36,210 candidates. V1 remains enabled
with automatic backtesting disabled and 1,200 forward rows; V2, ablation, and
regime remain disabled/not run.

The preflight package grants no authority: cutover review, activation, rollback,
runtime registration, production writes, risk mutation, and order authority all
remain false. No canonical/accounting/state/history/day-peak/recovery evidence
changed; no halt was cleared; no strategy, sizing, threshold, live, or AI
authority changed; no performance/backtest job was launched; and `/paper/run` was not
called. Rollback for PR #267 is code-only. Issue #202 remains frozen and Issue
#84 remains primary. Next, make the package reproducible from one immutable
read-only CI evidence bundle and a separately reviewable cutover decision
contract, while continuing to prohibit production writer registration or
activation unless the retained hold/halt are governedly resolved and the
separate cutover decision is explicitly reviewed.


## 2026-09-21 Issue #84 — digest-bound preflight evidence bundle — COMPLETE

PR #269 adds a canonical, SHA-256-addressed, read-only Stage F evidence bundle.
The bundle carries the exact runtime audit/status/fresh-day inputs, ledger
digest and revision, source and capture time, typed canary-gate evidence,
requested fraction, complete typed Stage D rollback receipt, exact deployed and
sentinel commits, and settled-deployment flag in one canonical JSON payload.
Loading the exported bundle revalidates its exact schema and digest and
recomputes the runtime binding, rollback readiness, canary plan, and complete
preflight package. Non-canonical JSON, unexpected keys, non-boolean gate or
authority claims, digest tampering, incomplete evidence, and cross-bundle
package substitution fail closed.

A separate decision-review contract binds the bundle and recomputed preflight
digests and exact blocker state. It is fixed at `pending_review`, cannot
self-approve, and cannot claim activation, runtime registration, production
writes, risk mutation, order, live, or ML authority. The current retained v5
validation hold and parity halt therefore continue to block cutover; this work
does not constitute the separately reviewed decision and does not activate a
writer.

Focused validation passed 45 Stage F regressions and 94 combined Stage B-F plus
successor-compatibility regressions. Compilation, repository validation,
structural/refactor audit, architecture ownership, architecture-debt comparison,
and exact-diff checks passed. The exact PR head
`54163b4ddab5edc460b81274cf87eb4039e6d053` passed all five applicable
exact-head workflows: Stage F, repository safety, architecture debt, the full
refactor/ownership/runtime/startup/research audit, and mandatory Change Safety
with exact Gunicorn smoke. PR #269 squash-merged as
`b73e8891889f1210ab357984b2e563d96fbc4f6d`; all post-merge gates and the
authoritative Splendid deployment passed.

The automatic post-merge snapshot was rejected as incomplete at 2/12 endpoints
while runtime workers were still registering. The safe read-only rerun after
settlement reached 12/12 and proved deployed/sentinel commit
`b73e8891889f1210ab357984b2e563d96fbc4f6d`. Sentinel is `pass/quiet` with zero
incidents and collection errors. The canonical ledger remains chain-valid at 88
immutable rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
accounting is `ok`, cash is `13429.13048559457`, equity is `13429.13`, positions
are empty, and day start/peak remain `13429.13048559457`. Market data and runner
pass. Self-check is warn only for the retained halt; the daily audit/risk remain
fail by design for that retained halt and validation hold. Shadow capture is
parity-pass and forward-ineligible at 1,428 cycles and 36,609 candidates. V1
retains 1,200 forward rows with automatic backtesting disabled; V2, ablation,
and regime remain disabled/not run.

No production StateStore writer was registered or activated; no canonical,
accounting, state, history, day-peak, or recovery evidence changed; no halt or
validation hold was cleared; no strategy, sizing, threshold, risk, order, live,
or AI authority changed; no research job was launched; and `/paper/run` was not
called. Rollback for PR #269 is code-only. Issue #202 remains frozen and Issue
#84 remains primary. Next, produce a current settled read-only bundle artifact
through CI and define the separately reviewed decision record, while retaining
all blockers and prohibiting writer activation until that review is explicit.


## 2026-09-21 Issue #84 — settled CI preflight artifact — COMPLETE

PR #271 implemented the next bounded Stage F evidence step. A new offline
builder consumes one authoritative read-only runtime snapshot, requires complete
12/12 endpoint classification, exact deployed/sentinel commit parity, a quiet
zero-incident sentinel, and settled Splendid status, then writes a canonical
digest-bound evidence bundle plus a separately digest-bound decision-review
record. Its only StateStore writes are inside a temporary sandbox used for the
typed rollback drill. The emitted decision is fixed at `pending_review`; it
cannot activate a writer or claim production, risk, order, live, or ML
authority. Forward-session, Stage B-E CI, repository, architecture-debt, and
refactor/startup evidence claims remain deliberately false in this runtime-only
artifact, so the current hold/halt continue to block cutover.

The first automatic post-merge capture demonstrated two fail-closed integration
defects without changing production state. Its four-attempt window ended at
2/12 endpoints while deferred startup was still loading at 137.8 seconds. A
safe read-only rerun then reached complete exact-head runtime evidence but the
bundle builder rejected `status_cash_provenance`: the authoritative paper status
preserved exact-precision cash while the v5 adapter required cent-rounded cash.
No artifact or approval was manufactured from either rejected run.

PR #272 corrected both bounded defects. Capture now permits eight finite
attempts separated by 45 seconds and has a regression that rejects an unbounded
loop. The v5 adapter accepts exact or cent-serialized cash/equity only within
the existing $0.005 serialization tolerance and rejects a $0.01 drift. PR #271
exact head `4b32b3b9315c1745fb47ce830ddcadf617ef5c5a` and PR #272 exact head
`58c75dddfe4aeed67d6b1cbfa56d0c54e8f878f0` each passed all five applicable
exact-head workflows: Stage F, repository safety, architecture debt, the full
refactor/ownership/runtime/startup audit, and mandatory Change Safety including
exact Gunicorn smoke. They squash-merged as
`f28cdf19635f04f54b58a131de0f553a971a8230` and
`e54775074a657f1c6ad3c0c6c2aad89799ca9a7e`, respectively.

The settled post-merge run for `e54775074a657f1c6ad3c0c6c2aad89799ca9a7e`
passed all five workflows, Splendid, and the new `research-snapshot` status. The
bounded collector observed three 2/12 loading captures before reaching 12/12 at
14:27 CDT. Sentinel proved the exact commit with no collection error. Accounting
remained `ok`; the canonical ledger remained chain-valid at 88 immutable rows
with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
market data and runner remained `pass`; and the retained validation hold and
risk halt remained true. The CI artifact was uploaded as ID `10659896468`
(archive SHA-256
`f967e1e97fe27806bc4f071cc29c0ad035c77fdd1636ef204fe615eefb6436b2`).
The bundle digest is
`a1f24a6ccc09dab9f918426f3c07878a763166121a16c15395bcea88ab30674e`;
the decision digest is
`4f1d8d05ff1015a11e6b69867c8459aea89311df72327de9f6646b4b5dc31d97`.
The decision correctly remains `blocked` by future-canary evidence, validation
hold release, and governed halt release.

No canonical/accounting/state/history/day-peak/recovery evidence was rewritten
or cleared; `/paper/run` was not called; no research job was launched; no
strategy, sizing, threshold, hard-risk, order, live, or AI authority changed.
Rollback is code-only and the generated evidence is immutable CI output. Issue
#202 remains frozen. Issue #84 remains primary; next, independently review the
digest-bound pending decision and continue single-owner cutover/rollback design
without registering a production writer until the reviewed decision and all
retained gates explicitly pass.


## 2026-09-21 Issue #84 — independent preflight artifact review — COMPLETE

The immutable CI artifact from settled refactor workflow run `35644406677` was
downloaded independently by artifact ID `10659896468`. Its ZIP SHA-256 exactly
matched the recorded archive digest
`f967e1e97fe27806bc4f071cc29c0ad035c77fdd1636ef204fe615eefb6436b2`.
The archive contained only the read-only runtime JSON/Markdown capture, canonical
cutover evidence bundle, and pending decision-review contract.

The downloaded runtime capture was passed through the repository's current
`build_cutover_preflight_artifact.py` in a new temporary sandbox. The regenerated
bundle and decision files were byte-for-byte identical to the archived files.
The independently reproduced bundle digest was
`a1f24a6ccc09dab9f918426f3c07878a763166121a16c15395bcea88ab30674e`,
the decision digest was
`4f1d8d05ff1015a11e6b69867c8459aea89311df72327de9f6646b4b5dc31d97`,
and the preflight remained `blocked` by exactly `future_canary_evidence`,
`validation_hold_released`, and `risk_halt_released_by_governed_evidence`.
The contract remained `pending_review` with every activation, production-write,
risk-mutation, order, live, ML, and runtime-registration authority false.

This review performed no production operation: the builder's only writes were
inside its temporary rollback-drill sandbox. No canonical/accounting/state/
history/day-peak/recovery evidence changed, no halt or validation hold was
cleared, `/paper/run` was not called, and no research or performance job was
launched. Issue #202 remains frozen. Issue #84 remains primary; the next safe
step is continued cutover/rollback design and accumulation of the missing
governed forward evidence, not writer activation or approval of this blocked
decision.


## 2026-09-22 Issue #84 — independent review settled acceptance — COMPLETE

PR #274 recorded the independent archive verification and byte-for-byte artifact
regeneration. Its exact head `a8a223a33803d70daa98f5b52cccb26009924ce8`
passed Change Safety, then squash-merged as
`922739fc3c856616541e617d27430f5a9c242848`. Post-merge Change Safety and
authoritative Splendid deployment settled green.

The first read-only post-deploy capture correctly remained incomplete at 2/12
endpoints while deferred startup was still registering. A later safe read-only
capture reached 12/12 at 08:09 CDT and proved the exact merged commit. Sentinel
was `pass/quiet` with zero incidents or collection errors. Accounting remained
`ok`; the canonical ledger remained chain-valid and projection-parity true at
88 immutable rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`.
Cash was `13429.13048559457`, equity was `13429.13`, positions and recent
trades were empty, and realized/unrealized P&L for the day were both zero.
Fresh-day baselines passed at the same exact cash/equity value. Market data and
runner passed with no active error. Shadow capture remained parity-pass and
forward-ineligible at 1,476 cycles and 37,692 candidates. V1 remained enabled
with automatic backtesting disabled and 1,200 forward rows; V2, ablation, and
regime remained disabled/not run.

The retained canonical-divergence halt and validation hold remain active, so
self-check is warn and the daily risk/audit outcome remains fail by design.
No halt or hold was cleared; no canonical/accounting/state/history/day-peak/
recovery evidence changed; `/paper/run` was not called; no research or
performance job was launched; and no production writer, order, live, or AI
authority was activated. Issue #202 remains frozen. Issue #84 remains primary;
continue the governed forward-evidence and cutover/rollback design work without
approving or activating the still-blocked decision.
