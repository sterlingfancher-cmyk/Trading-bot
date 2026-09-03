# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-09-03 06:08 CDT
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Validated runtime-code `main`: `6986f00fd2c38ab9be898eded5b5cb6e47904d84` (PR #169).
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
history, state/day-peak, live, ML, or order authority changed. Issue #96 remains
open for separately bounded future work; automated repair/self-healing remains
disabled, and any GitHub issue/draft-PR output must remain advisory and auditable.
