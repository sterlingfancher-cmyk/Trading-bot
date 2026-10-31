Warning: truncated output (original token count: 66994)
Total output lines: 4220

# Project Handoff — Authoritative Current Trading Runtime

Last updated: 2026-10-28 09:05 CDT
Repository: `sterlingfancher-cmyk/Trading-bot`  
Authoritative paper runtime: Splendid / `https://web-production-e1796.up.railway.app`  
Non-authoritative legacy state lineage: `https://trading-bot-clean.up.railway.app`  
Validated runtime-code `main`: `92c23ed45ea9abcf074956bb37d326239de47768` (deployed identically to Clean and Splendid; the services retain separate persistent state and are not economically comparable).
Active bounded evidence issue: #321 (fail-closed session performance evidence
adapter). Deferred engineering issue: #84 (authoritative single-owner StateStore / ledger
projection / valuation / risk cutover). Active frozen research issue: #202
(`hold_10d` read-only forward-shadow validation). Issue #222 is safely
reconciled under the verified-flat v5 validation hold; its prior discrepancy
remains unresolved and non-promotable.

## 2026-10-20 Issue #84 — production-writer interface contract — IN PROGRESS

Exact main remains `b7a2a99b931c24642800698dd94252ad63bee802` and no
competing repair PR is open. Scheduled run `39355742816`, runtime job
`118409979777`, passed on exact main. Artifact `12235675564` is bound to that
commit; its connector digest independently matches the downloaded ZIP SHA-256
`8f39638295d14b80611a37fa1e8bcd821da6d704ae54427b951fb6815488d3ff`.
The 2026-10-19 20:51:47 CDT observational snapshot is PASS with 13/13
reachable, sentinel quiet on exact main, self-check/audit/accounting/canonical
chain/parity/risk/runner/market data passing, and the account flat at cash
`13047.46948294168` / equity `13047.47`. The fresh risk day is not halted. The
immutable ledger remains chain-valid and parity-clean at 118 rows, digest
`0c521518fabcbd90745d8a61f78aec8a2ba2e7f3c9d1523f7843dd076047998b`.
Governed v5 remains active/pass. V1 remains running at 1200 rows; V2 and
ablation remain not-run; forward shadow is ineligible; Issue #202 / `hold_10d`
remain frozen. Standard capture still omits X-Ray, so whole-session no-entry
attribution remains inconclusive; no duplicate capture or research job was
launched.

The active branch is
`fix/issue84-production-writer-interface-20261020`. It adds the typed
`LedgerIntentWriter` protocol and a digest-bound
`ProductionWriterCutoverContract`. Inspection is read-only and requires a
candidate to accept the exact durable intent plus its journal record and
unchanged StateStore envelope; validate the full chain; recover partial appends
idempotently under an interprocess lock; and forbid caller-selected identity,
StateStore commit, order authority, runtime registration and production writes.
The resulting contract retains the existing
`canonical_execution_ledger.append_execution` owner and records five mandatory
blockers: independent cutover review, production adapter implementation,
single-writer runtime registration, StateStore commit coordination and a
default-armed rollback switch. It cannot self-approve, activate or hold paper,
live or AI execution authority, and inspection never invokes the candidate.

Focused production-contract, ledger-adapter, atomic-journal and single-owner
regressions pass 77/77. The staged full structural audit remains at 80 duplicate
groups, 137 informational findings, 32 critical findings and 104 warnings—the
same counts as accepted main—with no finding in the new module. Compile and
exact-diff checks pass. Impact-aware validation, remote publication and every
mandatory exact-head gate remain pending.

Next executable step: complete local impact-aware validation, publish one
focused PR and require every exact-head gate including both Gunicorn smokes.
This contract does not implement or activate a production adapter; that remains
a separately reviewed future seam after this contract is accepted.

## 2026-10-19 Issue #84 — durable-intent sandbox writer — MERGED; SETTLED DEPLOYMENT ACCEPTED

PR #311 was squash-merged as exact main
`b7a2a99b931c24642800698dd94252ad63bee802`. Its exact repaired PR head
`1f1ac5b7f76b422219e99f6f0f7edd1836697ca4` passed repository validation
`39268068336`, architecture debt `39268068476`, change safety `39268068428`
and refactor/runtime `39268068533`; both exact-head Gunicorn smokes passed.
Merge-head repository validation `39268428949`, architecture debt
`39268429099`, change safety `39268429082` and refactor/runtime
`39268429303` also passed, including both merge-head Gunicorn smokes. Runtime
job `118114801446` passed exact-head Splendid acceptance, read-only capture,
governed evidence build and artifact upload. Artifact `12193854528` has
independently verified ZIP SHA-256
`756f578562feded350b2f930f75683c922b1e7a856038c9067dfa84994a90dd9`.
The 2026-10-19 09:29:18 CDT settled snapshot is PASS with 13/13 reachable,
sentinel quiet on exact main, self-check/audit/accounting/chain/parity/risk,
runner and market data passing. The account is flat at cash
`13047.46948294168` / equity `13047.47`; the fresh risk day is not halted.
The immutable ledger remains chain-valid and parity-clean at 118 rows, digest
`0c521518fabcbd90745d8a61f78aec8a2ba2e7f3c9d1523f7843dd076047998b`.
Governed v5 is active/pass. V1 remains running at 1200 rows; V2 and ablation
remain not-run; forward shadow remains ineligible; Issue #202 / `hold_10d`
remain frozen. Standard capture still omits X-Ray, so whole-session no-entry
attribution remains inconclusive. No duplicate capture was launched.

The active branch is `fix/issue84-durable-intent-writer-20261019`. It adds a
separate `SandboxLedgerIntentWriter` that requires explicit sandbox I/O, the
typed `LedgerAppendIntent`, its exact digest-valid
`AppendIntentJournalRecord`, and the unchanged prior StateStore envelope. The
writer verifies the full existing chain and exact prior boundary, fixes every
row identity and hash from the durable intent, appends only the missing suffix
under an interprocess lock, fsyncs each row and directory, and deterministically
recovers a crash after any partial multi-row append. An already-complete retry
is byte-idempotent. Substituted records, StateStore drift, prefix/boundary drift,
precision drift, extra rows and any non-exact partial row fail closed before a
new mutation.

The focused proof now covers exact identity, restart idempotence, partial-append
recovery, substitution and divergent-prefix rejection, duplicate concurrent
callers, sandbox authority, and the full durable-intent → append → projection →
settled-journal handoff. Ledger-adapter, atomic-journal and single-owner tests
pass 63/63 locally. This remains a bounded shadow seam: it is not runtime
registered, cannot target production without explicit sandbox enablement, does
not call the production writer, commit StateStore, place orders, clear risk,
or change strategy/live/AI authority. PR #311's first exact head
`f9b92b92093d02283b3b5af765e594c1216c5375`
failed architecture run `39267264575`, job `118109993615`: artifact
`12194031586` proved that the new writer's nine-line process-lock body
duplicated the transaction-journal implementation, adding exactly one
duplicate-function group and one informational finding, with no new critical
or warning findings. The bounded repair uses an equivalent context-managed
file lock. Focused writer tests pass 19/19, and the full structural report
returns duplicate groups from 81 to the base 80 and info findings from 138 to
137 while critical/warning totals remain unchanged. The validated final writer
blob is `f1898c9215846660ef5cf70da1c55698ab44c3e1`; no failed old-head workflow
was rerun. The next separately reviewed interface contract is active above;
PR #311 did not activate a production writer or StateStore commit.

## 2026-10-17 Issue #84 — recoverable intent-to-transaction handoff — MERGED; SETTLED DEPLOYMENT ACCEPTED

PR #310 was squash-merged as exact main
`3d4b478c290a5b10cda2e93aba8b7abea3b7eea9`. Its exact PR head
`f75ee82bb4dd3e5cb633be068c5df6fc4d6c2cb1` passed all mandatory gates:
repository validation `39039053176`, architecture debt `39039053185`, change
safety `39039053114`, and refactor/runtime `39039053113`; both exact-head
Gunicorn smokes passed. Merge-head repository validation `39039174616`,
architecture debt `39039174540`, change safety `39039174663`, and
refactor/runtime `39039174553` also passed their code gates and both Gunicorn
smokes. Runtime job `117415182117` passed the explicit exact-head Splendid
deployment-acceptance step for `3d4b478c...`, completed its read-only capture,
governed evidence build and artifact upload, and settled successfully. Artifact
`12103532158` has verified ZIP SHA-256
`9acdf00c50477b80ae9d8941342c67df67d4bd5745f1ba4e9f890cf4099cd2cd`.

The pre-merge fresh scheduled workflow
`38990420815`, runtime job `117271370876`, completed successfully on that
then-current main `d424db...`. Artifact `12084343044` has independently
verified ZIP SHA-256
`51125ee010906559e14595352ef5389eab72647c8b3caa43a6c48d24312b4e6d`.
Its observational snapshot was generated 2026-10-16 at 20:20:30 CDT and is
WARN solely because the hard daily-loss protection is active. All 13 surfaces
are reachable; application/listener readiness, sentinel, runner, market data,
accounting and canonical chain/projection pass. The account is flat at cash
`13047.46948294168` / equity `13047.47`, with realized-today P/L `-723.82`.
The canonical ledger is chain-valid and parity-clean at 118 rows with digest
`0c521518fabcbd90745d8a61f78aec8a2ba2e7f3c9d1523f7843dd076047998b`.
The terminal SNOW short entered at `310.80` and exited at `528.61`, realizing
`-723.82`; the 3% absolute daily-loss halt correctly latched at 5.256% realized
loss / 5.337% peak drawdown. No halt was cleared and no state, history, risk
limit or execution evidence was changed. Performance V1 remains running at
1200 rows; V2 and ablation remain not-run; forward shadow remains ineligible;
Issue #202 / `hold_10d` remain frozen. The standard capture still omits X-Ray,
so it does not prove whole-session coverage or the cause of the prior all-day
no-entry session.

The merged implementation adds a digest-bound
`TransactionJournalHandoffReceipt` and a sandbox-only
`SandboxAppendIntentJournal.handoff_projection(...)` transition. After an
exact immutable append has already been observed and projected, the handoff
serializes one coordinator lock, verifies the original intent and transaction
identity, durably binds the intent, prepares the exact canonical transaction
journal and advances it to `ledger_settled`. Each write is independently
idempotent, so retry closes crashes after intent binding, transaction prepare
or transaction settlement. Substitution, conflicting identity, cross-directory
journals and divergent ledger/execution evidence fail closed.

This is a bounded shadow architecture repair, not production writer
activation. It does not call the canonical ledger writer, commit StateStore,
register runtime authority, place orders, change strategy/risk behavior, clear
the retained halt, rewrite evidence or grant live/AI authority. The descriptor
continues to report `invokes_production_writer=false` and
`commits_state_store=false`; it now reports only the reviewed journal-to-journal
handoff as ready with `handoff_recovery=idempotent_stepwise_retry`. Focused
atomic-journal, ledger-adapter and single-owner regressions pass 55/55 locally.
Local impact-aware validation also passed at its exact local commit: 99
architecture/policy tests plus 55 focused regressions, with zero new critical
findings. The remote branch was exactly one commit ahead / zero behind main,
and the three published blobs matched their local Git object IDs.

The subsequent separately reviewed writer-adapter seam is now active above;
no runtime cutover or StateStore commit is authorized by this handoff.

## 2026-10-16 Issue #84 — durable pre-append intent journal — ACCEPTED; HANDOFF NEXT

PR #309 was squash-merged as exact main
`d424db053363dc05a5f56b3945cdfcdbb075853a`. Its exact PR head
`8f5a68d20d7490177a99bc21e8eaf72f2fe32e37` passed Repository workflow
`38912964748`, Architecture workflow `38912964772`, Change Safety workflow
`38912965023` and Refactor/runtime workflow `38912964700`. Both required
exact-head Gunicorn smokes passed. The merge head passed Repository workflow
`38913329582`, Architecture workflow `38913329320`, Change Safety workflow
`38913330056` and Refactor/runtime workflow `38913329220`. Runtime job
`117014941259` completed successfully: exact-head Splendid deployment
acceptance, the read-only capture, governed evidence build and artifact upload
all passed. Acceptance artifact `12052105469` has independently verified ZIP
SHA-256
`89dba92b640fefbbda3dde28e338a7bf7b2ab0d3438ed4ca9334721ddf828ce5`,
acceptance digest
`dd688437b025854f7646d7431afb8ceddac0baad5a40a7ad03a35ca72065ea32`
and decision digest
`54863f7ecec955730cc464d5e6743fa9ec7a269c85a7ea21f86f20e09a3738b0`.

The settled acceptance capture was generated on 2026-10-16 at 09:14:49 CDT.
All 13 read-only surfaces are reachable; listener/application readiness,
self-check, compact audit, accounting, canonical chain/projection, risk,
runner, market data and sentinel pass. The account is flat at cash
`13771.293025192768` / equity `13771.29`, with realized-today P/L `0.0`.
Risk is not halted and the fresh risk baseline is clean at the same equity.
The canonical ledger is chain-valid and parity-clean at 116 rows with digest
`ad1b56f81fa98efb98419d6695352c2129d2cb80cbb4cd747297e824dc3406d1`;
the latest MRNA entry/exit lifecycle is terminal. Governed v5 remains
active/pass. Performance V1 remains running at 1200 rows; V2 and ablation
remain not-run, and forward shadow remains ineligible, so Issue #202 /
`hold_10d` stay frozen. The standard capture again omitted the X-Ray endpoint.
It cannot establish whole-session X-Ray coverage or the cause of an all-day
no-entry session; that investigation remains inconclusive.

The accepted change adds a separate sandbox-only
`SandboxAppendIntentJournal` for the typed
`LedgerAppendIntent` introduced by PR #308. The journal durably records the
pre-append identity contract before any append, binds only the exact settled
`LedgerProjectionObservation`, permits an abort only while both the immutable
ledger boundary and StateStore payload remain exact, serializes the active
owner across processes, is restart-idempotent and archives terminal records
immutably before slot reuse. Record digests cover the intent, prior boundary,
StateStore digest, execution identities, phase and settled ledger digest.
Substitution, tampering, boundary drift, StateStore drift and conflicting
owners fail closed.

This is still an intermediate shadow architecture repair. It deliberately
does not hand off to the existing settled transaction journal, invoke the
production writer, commit StateStore, register in the runtime, place orders,
change risk/strategy behavior, clear a halt or grant live/AI authority. Its
descriptor reports `transaction_journal_handoff_ready=false`,
`invokes_production_writer=false` and `commits_state_store=false`. Focused
atomic-journal, ledger-adapter and single-owner regressions pass 49/49;
the impact-aware audit passed 99 canonical invariants plus the 49 focused
tests. Exact-diff review, every mandatory exact-head and merge-head gate, both
Gunicorn smokes, review, merge and settled Splendid acceptance are complete.

Next executable step: implement the subsequent bounded seam on a fresh branch
from exact current main—an explicit atomic handoff from this durable intent
journal through the production append into the settled transaction journal.
Require focused crash-window, duplicate, restart and concurrency regressions;
do not claim write-ahead completeness or activate the writer before that
separately reviewed transition exists.

## 2026-10-15 Issue #84 — settled projection recovery; pre-append intent — IN PROGRESS

PR #307 is fully settled on exact main
`957d418f90fda012eaf475916b77a8d48aa808c2`. Merge-head Refactor/runtime
workflow `38579024169`, job `115904303637`, completed successfully with every
step passing, including exact-head Splendid acceptance, the 13/13 read-only
capture, governed evidence construction and artifact upload. Artifact
`11901713838` has independently verified ZIP SHA-256
`36433024dca4f61251b3290ddbad85e96fb79e1007c6d44bba5e65324372fbd9`,
acceptance digest
`0383a18c15396c367dd01c8b826552f6e0847507eb5a2a173708ac89f49c80c4`
and decision digest
`52ca9111aef5cff16f4a0a98e2967af6ad44078d657ee2675c054c861b887703`.

The observational capture is clean: self-check, compact audit, sentinel,
runner, market data, accounting, canonical chain/projection and risk pass;
governed v5 is active/pass; risk is not halted; and the account is flat at
cash `13772.372185594942` / equity `13772.37`, with realized-today P/L
`-5.15`. The canonical ledger is chain-valid and parity-clean at 112 rows with
digest `0bdbbca838c5a9f901eb583fe7761c6464644ad2c7bd2142dbb7c9cd3081b52d`.
The two new terminal rows form an ordinary ZS entry/exit lifecycle. Performance
V1 remains running at 1200 rows; V2 and ablation remain not-run, and forward
shadow remains ineligible, so Issue #202 / `hold_10d` stay frozen. The standard
capture still did not request `/paper/entry-pipeline-xray-status`; it does not
establish whole-session X-Ray coverage or the cause of an all-day no-entry
session.

The active branch is `fix/issue84-preappend-intent-20261015`. The next bounded
gap is now explicit: the reviewed journal can bind and recover an already
settled immutable append, but the production ledger writer still creates its
UUID, timestamp and hashes internally, so the system has no typed pre-append
identity contract. The branch adds a shadow-only `LedgerAppendIntent` that
binds the exact current StateStore payload, immutable ledger boundary, strict
next sequences and complete execution identities before an append. Intent
preparation rereads and verifies the full ledger and refuses a stale boundary.
A later append can be promoted to projection evidence only when its prior
boundary, StateStore digest and every execution field exactly match the
intent; substitution, sequence drift, ledger movement and StateStore drift
fail closed.

This is an intermediate architecture repair, not writer activation or a
completed write-ahead journal. The descriptor explicitly reports
`production_writer_accepts_intent=false` and `write_ahead_journal_ready=false`.
It performs no ledger/state write, runtime registration, order action, risk or
strategy change, live action or AI authority grant. Focused ledger adapter,
single-owner transaction and atomic-journal regressions pass 42/42; compile
and whitespace checks pass. Exact-diff review, impact-aware validation,
mandatory exact-head workflows, both Gunicorn smokes, review, merge and
settled Splendid acceptance remain pending.

Next executable step: publish this exact branch as the single Issue #84 repair
path, open its PR, run every mandatory exact-head gate, and review the exact
diff. If all gates pass, merge and require merge-head gates plus settled
read-only Splendid acceptance. The subsequent bounded seam is persistence of
the typed intent in the sandbox journal and an explicit writer handoff; do not
claim write-ahead readiness or production activation before those separately
reviewed stages exist.

## 2026-10-14 Issue #84 — PR #306 accepted; projection-bound recovery — IN PROGRESS

PR #306 is fully settled on exact main
`f0efd1fee7887a90cda4609c0f8986f8df6d7045`. Runtime workflow
`38411546562`, job `115345596302`, completed successfully after the prior
checkpoint. Every job step passed, including exact-head Splendid acceptance,
the 13/13 read-only runtime capture, governed evidence construction, artifact
upload and research snapshot status. Artifact `11821698070` has ZIP SHA-256
`fccb792dc66f36c8bb8f47df604126c53f6b28288fb4d0aa93ccdd3f08a72b41`;
its deployed commit is exact, acceptance digest is
`3b83e1e3f0ac9bd81de137872fec170ffb4123869da09e6db57bf8c285fef026`
and decision digest is
`3cbc1645bbcec8b41359187d4263c382e3e0fcc1b4b68e3e6198b8524802ad56`.

The accepted capture is clean and observational: self-check, compact daily
audit, sentinel, runner, market data, accounting, ledger chain/projection and
risk all pass; the account is flat at cash/equity approximately
`13777.52048 / 13777.52`; risk is not halted; governed v5 is active/pass; and
the canonical ledger remains 110 rows / 22 current-epoch rows with digest
`bf7bf548ddf0562e015e32d60f52b5a7839792b3bac756b111d52029c22b2d4a`.
Performance V1 remains running at 1200 rows; V2 and ablation remain not-run,
and forward shadow remains ineligible, so Issue #202 / `hold_10d` stay frozen.
The capture did not request `/paper/entry-pipeline-xray-status`; consequently
the new 120-cycle X-Ray retention is deployed but no whole-session coverage or
all-day cause is claimed. Ordinary cycles must populate and a later read-only
observation must inspect that exact endpoint.

The next bounded Issue #84 seam was then resumed on branch
`fix/issue84-projection-recovery-binding-20261014`, implementation commit
`623e7b4ff40b9bf729e64779fa68516d7d9a0016`. The sandbox journal's post-append
settlement and recovery can no longer pair a reviewed `LedgerProjectionObservation`
with a separately caller-constructed `ObservedLedgerState`; new typed methods
derive the row counts, epoch counts, digest and execution IDs directly from the
already validated projection observation. Existing journal binding and
StateStore revision checks remain fail-closed. This is shadow/sandbox-only: it
does not append or rewrite the canonical ledger, register with runtime, change
production state, place orders, change strategy or risk, or grant live/AI
authority.

Local compile and three direct focused regressions pass. The 21-test Change
Safety gate suite, repository/Railway validation, structural audit,
architecture ownership, typed configuration and architecture-debt checks pass
with zero new critical or warning findings. The local environment has no
pytest, so the complete focused pytest suite and all exact-head workflows,
including both exact Gunicorn smokes, remain required on the published PR.
No `/paper/run`, halt clear, runtime mutation or order action was attempted.

Next executable step: publish this exact branch/head, open the single Issue #84
repair PR, and require every mandatory exact-head workflow and both exact
Gunicorn smokes. Review the exact diff and merge only if all gates pass; then
require merge-head gates and settled exact-commit Splendid acceptance.

## 2026-10-13 Issue #84 — all-day entry diagnostics — ACCEPTED

The October 12 evidence review is complete. The reason-bearing Entry Pipeline
X-Ray persisted only 25 full cycles, approximately 125 minutes at the configured
five-minute cadence. Runtime shadow capture retains 30 cycles but its history
rows omit terminal rejection reasons. Scanner and blocked-entry audit surfaces
are latest-snapshot oriented. Therefore the existing durable evidence cannot
attribute the entire October 12 no-entry day; the 15:40 CDT late-day cutoff and
quality/extension reasons remain valid only for that observed late cycle.

Active branch `fix/issue84-all-day-entry-diagnostics-20261013` adds compact,
timestamped reason rows to the existing X-Ray telemetry owner. It retains at
most 120 rows (ten hours at five-minute cadence), excludes full symbol and
blocked previews, declares first/last observation and maximum observed gap,
and refuses whole-session attribution unless retained rows span 08:30 through
the last expected 14:55 invocation without a gap beyond 2.5 configured
intervals. The status contract says explicitly that the latest cycle alone
never proves a whole-session cause. The existing reliability overlay delegates
to the same helper inside its reviewed transactional `update_state` boundary;
no new writer, route, wrapper, report compiler, order path, trading threshold,
risk limit, live authority or AI authority is introduced.

Focused compile, exact-diff/whitespace review and six direct state/coverage
regressions pass locally. The mandatory audit's 104 unittest invariants pass;
the local environment does not contain pytest, so its pytest phase stopped
before running the three standing Issue #84 suites or the new focused suite.
The focused suite is now selected explicitly for decision-path changes, and its
canonical pytest execution remains an exact-head CI requirement. A fresh
read-only runtime attempt was rejected before network access because the only
repository URL is a Railway-hosted domain and this execution environment
prohibits treating Railway access as the authoritative Splendid reader. This
is a specific runtime-read access-path failure, not a claim that GitHub or all
Splendid evidence is unavailable, and it does not supersede the accepted
October 12 Splendid capture. Exact-head workflows, both Gunicorn smokes,
review, merge-head gates and settled post-deploy Splendid acceptance remain
pending. No `/paper/run` call, halt clear or runtime mutation was attempted.

Next executable step: publish this exact branch/head and open the single repair
PR; run every exact-head mandatory workflow and both smokes. If all pass,
review and merge, require merge-head gates and settled Splendid acceptance, then
resume Issue #84's composition-to-journal/recovery dependency.

## 2026-10-12 reporting retrieval repair and entry investigation

PR #305 is settled on main `75d4b95fc44fb70b8cca2e8c9027416506295ec1`;
Issue #84 comment 6126363791 records exact-head and merge-head acceptance.
Do not repeat its implementation or interpret pending architecture cutover as
a halt on current governed paper execution.

Fresh observational Splendid reads at 15:36–15:42 CDT succeeded through direct
HTTPS using Python urllib/curl. Compact daily audit: cash 13777.52047869751,
equity 13777.52, realized today 0, unrealized 0, no positions; risk not halted,
runner enabled without active error, complete accounting coverage and clean
110-row/22-current-epoch ledger parity. Journal timestamps establish six
executions on October 9 (SNOW entry/partial/full exit; QQQ/ANET/ZS full exits),
and none October 12. Missing report retrieval is not evidence of zero trades.

Updated the existing pre-close automation, without changing cadence: collect
runtime first; bounded direct HTTPS and one alternate transport; parse compact
and full audit schemas; filter journal timestamps in America/Chicago; retain
successful account fields even when GitHub or a separate P/L field fails.
Save confirmed by automation update. Future scheduled delivery is not yet
verified, and the prior task's precise transport error remains unknown.

The stored /paper/reports?full=1 payload is historical: last end-of-day report
September 12, no intraday history. Current-source run_report_guard.py defers
store_compiled_report during ordinary cycles to protect runner latency. Do not
turn heavy inline reports back on or call compiling routes to manufacture a
fresh report. Use live observational account/journal evidence for summaries.

At 15:40 CDT the blocked-entry and quality diagnostic surfaces showed the last
cycle's late-day cutoff plus extension/quality rejections. app.py explicitly
sets feedback self-defense during the final 30 minutes and drops that cutoff
after close; this explains the late-cycle reason versus post-close risk status.
It does not prove the cause of all earlier October 12 no-entry cycles. The
existing scanner audit overwrites the last cycle; shadow history retains counts
but not historical rejection reasons. No demonstrated execution defect or
justification for changing thresholds/hard-risk limits was established.

Next executable work: add bounded, timestamped, read-only-consumed per-cycle
rejection evidence through the existing telemetry owner, with a day/session
coverage declaration so a partial last-cycle snapshot cannot explain an entire
day. Check existing durable research captures before adding storage; retain
paper/risk/ledger authority boundaries. Then resume Issue #84's reviewed
composition-to-journal/recovery dependency. No production code or state was
changed in this reporting repair; this checkpoint is not deployment evidence.

## 2026-10-12 Issue #84 — exact ledger-to-projection composition — IN PROGRESS

Fresh read-only Splendid evidence on exact deployed main
`9d529ad23078bd35dc99d55c42f0737cf9f03859` is clean: 13/13 endpoints are
reachable; self-check and daily audit pass; sentinel is quiet/pass with zero
incidents; runner and market-data accounting pass; governed v5 is active/pass;
risk is not halted; and the account is flat at cash/equity approximately
`13777.52048 / 13777.52`. The canonical ledger remains chain-valid and
projection-parity-valid at 110 rows / 22 current-v5 rows with digest
`bf7bf548ddf0562e015e32d60f52b5a7839792b3bac756b111d52029c22b2d4a`
and zero accounting coverage/economic issues. Performance V1 remains running
at 1200 forward rows; V2, ablation and regime are not-run, so Issue #202 /
`hold_10d` remain frozen.

The active branch is `fix/issue84-single-owner-orchestration-20261012`. The
next bounded single-owner gap is the remaining caller-controlled seam between
the reviewed immutable-ledger adapter and the reviewed projection transaction:
a caller could derive an append observation, then separately construct the
transaction inputs. The repair adds one shadow-only adapter composition method
that derives the typed append observation and immediately feeds those exact
executions and that exact proof into the single-owner accounting / protected
valuation / risk / next-StateStore-revision transaction. A typed composition
receipt proves that the transaction retained the observed append proof. It
does not append or rewrite the ledger, commit state, register with the runtime,
place orders, activate a production writer, change risk limits, or grant live
or AI authority. Missing marks and all existing malformed, tampered,
duplicate, cross-epoch or boundary-drift evidence continue to fail closed.

Focused adapter, projection and atomic-journal regressions pass 35/35; compile
and whitespace checks pass. Impact-aware repository validation, mandatory
exact-head CI, review, merge-head gates and settled Splendid acceptance remain
pending. No paper cycle was forced, `/paper/run` was not called, no halt was
cleared and no immutable runtime evidence changed.

## 2026-10-10 Issue #84 — merge-head acceptance receipt vocabulary — IN PROGRESS

PR #303 exact head `93072b0b7c069406d82c713468b1ba737598d07e`
passed all four mandatory exact-head workflows and both exact Gunicorn smokes,
then squash-merged as `0b5ca049fb7a9ddfc9ad25e53a191256ab5fc769`.
All merge-head code gates and both smokes passed, exact Splendid deployment
settled, and the 13/13 read-only capture passed. The governed evidence builder
then failed closed only on
`latest_execution_receipt_matches_ledger`. Artifact `11672363322` has ZIP
SHA-256
`80506c6a75cee535f65b45be0c6212f19f989b95e2e8f1bd8bbd2153a26b2e8c`.

The exact capture proves the canonical ledger and receipt agree at row 110,
including execution id `37e06d4bb5654a1a8d19cf12a0379686`; chain,
state projection and accounting are clean, the account is flat, governed v5 is
active/pass and risk is not halted. The false negative is a bounded vocabulary
drift: the builder accepts only `entry` and the nonexistent generic `exit`,
while the reviewed coordinator emits `entry`, `partial_exit`, `full_exit`,
`market_surge_deployment` and `market_surge_queue`. The active repair is
`fix/issue84-post-start-tail-acceptance`: admit exactly those five installed
coordinator operations while retaining exact row-count, execution-id, intent,
chain, parity, accounting and governance checks. Unknown operations still fail
closed. No execution, halt clear, state/history rewrite, risk-limit change,
live enablement or AI authority is involved.

## 2026-10-10 Issue #84 — canonical ledger evidence adapter — IN PROGRESS

Fresh read-only Splendid evidence on exact deployed main
`8e24cf50b376c76cc97664eec682b10ce54e4b81` is clean: 13/13 endpoints are
reachable, self-check and daily audit pass, sentinel is quiet/pass with zero
incidents, governed v5 is active/pass, and risk is not halted. The account is
flat at cash/equity approximately `13777.52048 / 13777.52`. The canonical
ledger advanced through ordinary governed lifecycle activity to 110 rows / 22
current-v5 rows, digest
`bf7bf548ddf0562e015e32d60f52b5a7839792b3bac756b111d52029c22b2d4a`,
with a valid chain, exact state-projection parity, zero missing rows and clean
accounting. Performance V1 remains running; V2, ablation and regime are
not-run, so Issue #202 / `hold_10d` remain frozen.

The active branch is `fix/issue84-cutover-commit-activation`. The demonstrated
architecture gap is that the reviewed single-owner transaction still accepts a
caller-constructed `LedgerAppendProof`; it has no typed adapter that derives
that proof from the immutable production ledger format. The bounded repair
adds a read-only, explicit-path `trading.ledger` adapter. It verifies the full
hash chain and unique execution IDs, proves the prior prefix digest/terminal
hash/epoch boundary unchanged, binds that boundary to the current immutable
StateStore envelope, converts only same-epoch entry/exit/partial-exit rows into
typed execution snapshots, and emits the exact append proof consumed by the
existing shadow transaction. Missing, malformed, tampered, duplicate,
cross-epoch, empty or state-mismatched evidence fails closed. The adapter has
no append, state write, environment, runtime registration, order, live or AI
authority. Change Safety now selects its focused regression.

Local validation passes 54/54 focused ledger-adapter, single-owner transaction,
atomic journal and Change Safety tests plus the complete 99-test impact-aware
suite. Repository, Railway configuration, structural architecture, ownership,
typed-configuration and architecture-debt gates pass with zero new critical or
warning findings. The local exact Gunicorn smoke did not reach `ready` because
its startup provider probes were rate-limited for SPY and QQQ; this is
incomplete, not a pass, and the mandatory exact-head CI smokes remain required.
Exact-head CI, review, merge and settled Splendid acceptance remain pending. No
paper cycle was forced, `/paper/run` was not called, no halt was cleared and no
immutable runtime evidence or hard-risk limit changed.

## 2026-10-07 Issue #84 — governed full-exit wrapper abort — IN PROGRESS

A fresh 13/13 read-only Splendid capture on exact deployed main
`242c1221442ff7d8a457b3b6ad409895b511b379` found a new active runner error:
`TypeError: _wrap_exit.<locals>.wrapped() got an unexpected keyword argument
'_governed'`. The governed operation failed before canonical append, correctly
restored state and latched the fail-closed risk halt. The canonical ledger is
chain-valid at 99 rows with digest
`f06507675ad47f45d4a364358f095d690086f2d2a49c5ad23b49623401dca61f`;
accounting reports zero coverage and economic issues, and equity is
`13952.04`. No halt was manually cleared and `/paper/run` was not called.

PR #296 exact head `79e71ab387f29527a8b7da6a527b0cd8c5217b7a`
passed all four PR workflows and both exact Gunicorn smokes, then squash-merged
as `48d754220056ddf25d41e38e5813d5455985b672`. All four merge-head code
workflows and both Gunicorn smokes passed, and Splendid settled that exact
commit. Runtime workflow `37634184262`, job `112836535686`, captured all 13
read-only endpoints but failed closed in the governed evidence builder because
the fail-closed halt remained. Artifact `11487569435` has ZIP SHA-256
`2f829af02ecfc2418be5d9c6855f2737caa6be01522a6afee871aaaa2933168b`.

PR #297 exact head `d15cf015f1fb93c10076cea747645b995c43bc8a`
passed all four PR workflows and both exact Gunicorn smokes, then merged as
`5cc8aa26ed8f1679a53c316319003ca8e6c7e748`. All four merge-head code jobs
and both Gunicorn smokes passed; exact Splendid deployment and a 13/13 read-only
capture also passed. Runtime job `112846484055` nevertheless failed closed in
the governed evidence builder. Artifact `11490227329` has ZIP SHA-256
`a827ddee524ba4a1ca02cf90634f5e77101703a2db54f1c83f256f450749c66e`.

That artifact supersedes the earlier incident signature: at
`2026-10-07 09:27:59 CDT`, the next full-exit attempt reached the separately
installed pattern-recognition wrapper and aborted with
`TypeError: apply.<locals>.patched_exit_position() got an unexpected keyword
argument '_governed'`, intent
`ae64864e8f8abe8bfd34c28e2dbf6e062842d3303c3777a2191b629cd9423cbe`.
State restored true; the chain-valid/parity-valid ledger remained at 99 rows
and digest `f06507675ad47f45d4a364358f095d690086f2d2a49c5ad23b49623401dca61f`;
the correctness halt remained latched. PR #297 correctly refused to recover a
different incident. The durable checkpoint is Issue #84 comment `6040267944`.

PR #298 exact head `3d97cf391ae193c271eb1a1dbe317bf0f7af18a3`
passed all four workflows and both exact Gunicorn smokes, then merged as
`6b9b29421682517bbeda49881f7112afcfb5254f`. All merge-head code gates and
both smokes passed; exact Splendid deployment and the 13/13 read-only capture
also passed. Runtime job `113350447691` nevertheless failed closed in the
governed evidence builder. Artifact `11555831526` has ZIP SHA-256
`b10ce8a23a34c15027b6091cd258063673048d56b69714cdf34de78b0ed270ec`.

Before PR #298 deployed, the prior code emitted one later instance of the same
pattern-wrapper abort at `2026-10-08 08:56:48 CDT`, intent
`659dc62bfb73bf6331d1cf38b3252a31f339ca54a16e0f4656ddc8b6a409b132`.
The immutable boundary remained 99 rows with the same ledger digest, valid
chain/projection parity and `state_restored=true`; runner active error is now
false and sentinel is quiet/pass on exact `6b9b294...`. The halt stayed latched
because the exact matcher correctly rejected the superseding incident. Issue
#84 comment `6061648816` is the durable independent record.

PR #299 exact head `950697ae56d48ff9c885078e07757bfd5384b0d8`
passed all four workflows and both exact Gunicorn smokes, then merged as
`86125e6fb39a1f528dd5989e037def25d9fe9ea1`. All merge-head code gates and
both smokes passed; exact Splendid deployment and 13/13 capture passed. Runtime
job `113356528689` failed closed in the evidence builder. Artifact
`11556283342` has ZIP SHA-256
`1674c8b3219f7aa91e341662b300fa125f84de00f5d4612511914a34a1ed1f82`.

The exact abort signature remained intact, but two lawful governed
risk-reducing actions advanced the chain-valid/parity-valid ledger after the
99-row incident boundary: full exit COIN and partial exit ZS. Current ledger
rows are 101, current epoch/state rows are 13/13, digest is
`179169d3475a1577ead56acd0395ae07fb4ffa6f336ed262cb7dd4a43b73d825`,
accounting is clean, runner active error is false, and sentinel is quiet/pass on
exact `86125e6...`. The static 99-row recovery requirement was therefore stale;
repeatedly rebinding the latest digest would race legitimate risk-reducing
lifecycle progress. Issue #84 comment `6061952775` is the durable checkpoint.

The active branch is now `fix/issue84-forward-exit-recovery-proof`. It preserves
the exact incident row/digest boundary but accepts a bounded post-incident delta
only when every added parity-matched state row is an `exit` or `partial_exit`,
the ledger remains chain-valid with no missing rows, current-epoch/state counts
match the delta, accounting and positions reconcile, the latest governed
receipt is exact, and hard-risk limits remain unchanged. Any entry, malformed
row or unbounded delta fails closed. Positive forward-exit and post-incident
entry rejection regressions are included. Exact-head workflows, merge,
deployment and settled acceptance remain pending.

PR #300 exact head `22562d2a6321f817dc29320cc669727d66bdb329`
passed all four exact-head workflows and both exact Gunicorn smokes, then
squash-merged as `a0032863385a43f2e5eb03412bbb2d3180b55dee`.
All four merge-head code gates and both smokes passed; exact Splendid deployment
and the 13/13 read-only capture also passed. Runtime job `113365955780` failed
closed only in the governed evidence builder. Artifact `11557756865` has ZIP
SHA-256
`176f4321f6dbf00cd23b4ff05bf0054297c2d105f88a9272a02f7bea3e4a6602`.

The captured runtime is otherwise unchanged and internally clean at 101 rows,
13/13 current epoch/state rows and digest
`179169d3475a1577ead56acd0395ae07fb4ffa6f336ed262cb7dd4a43b73d825`.
The v4 successor did not run because the prior v3 failed recovery diagnostic is
itself the current halt detail, while the matcher still required the older v2
diagnostic shape. The exact v3 diagnostic is independently captured: version
`governed-v5-runtime-full-exit-abort-recovery-2026-10-08-v3`, with only
`canonical_digest_exact`, `canonical_rows_exact`, and
`last_execution_receipt_exact` false and every other check true. The active
repair branch is `fix/issue84-v3-failure-successor`; it changes only this
predecessor-signature gate, requires the complete exact check-key set and
failure tuple, and rejects near matches.

PR #301 exact head `df3e7ddbb2cbe70d565da69b9741daea20ec39e8`
passed repository validation and the full refactor/ownership/configuration
workflow, including the exact Gunicorn smoke. Its focused regressions and the
Change Safety Gunicorn smoke also passed, but Architecture Debt run
`37794178160` failed because the new predecessor-drift test used a direct
dictionary mutation that increased `dynamic_mutation_targets` by one. Change
Safety run `37794179992` therefore failed only its final aggregate decision.
Artifact `11558196311` records the exact architecture violation; artifact
`11557632639` records every other Change Safety component as successful. The
same PR branch now parameterizes the fixture to exercise predecessor-version
drift without adding a new mutation target. No production runtime or authority
changed. Require a fresh completely green exact-head rerun before merge.

The repaired PR #301 exact head
`41f06f7df04c07a0d37e329b78e3d5cec9cd20ac` passed all four exact-head
workflows and both Gunicorn smokes, then squash-merged as
`602adc4a616d89fd49aeecb01012612aa110ad19`. All merge-head code gates and
both smokes passed; exact Splendid deployment and 13/13 read-only capture
passed. Runtime job `113858483334` failed closed only in the governed evidence
builder. Artifact `11622900618` has ZIP SHA-256
`cfd407c5b094497d9e3df234353ad758fe4e0efa060814ba2d70a36522f3d70e`.

The exact capture proves the risk-day transition had already released the
transient halt without deleting the immutable discrepancy or exact v3 failed
recovery diagnostic. Governed status is active/pass, risk halt false, chain and
projection parity valid, accounting clean, and the canonical ledger is 104
rows with 16/16 current epoch/state rows and digest
`6e7142bd1dfb4accb1ecda49c4ab0489f02f88142ad9badcaa23acce59d49d94`.
All five rows after the 99-row incident are current-epoch canonical
risk-reducing actions: one partial exit and four full exits. The latest exact
receipt is a full exit at row 104. The v4 recovery did not write its receipt
because its matcher required the halt to remain active. The active repair is
`fix/issue84-already-released-recovery-receipt`: admit only the exact
already-released active state with no existing receipt, then rerun the same
chain/parity/accounting/current-receipt/tail proof and record the non-destructive
recovery receipt. No execution or halt clear is performed by this successor.

## 2026-10-06 Issue #84 — post-start forward-execution acceptance repaired and accepted

PR #294 exact head `9187428ca75654eea9355f7fb320273fdd5bcc73`
passed all four PR workflows after the three jobs cancelled before acquiring a
runner were retried; both exact-head Gunicorn smokes passed. It squash-merged
as `3c152d53821f257e92422e98170a6af92571664e`. All four merge-head code
workflows and both exact Gunicorn smokes passed, and Splendid settled that exact
commit. Runtime workflow `37476564248`, job `112314047819`, then captured a
complete 13/13 exact-head read-only snapshot but failed closed at `Build
governed pre-start or post-start evidence` with
`governed restart post-start evidence blocked: accounting_clean_and_flat,
canonical_ledger_unchanged`. Artifact `11419208661` has ZIP SHA-256
`bc23fdfef7ab304d01e07383c514e801dc4a45ae97a22a49e9c63661860160ea`.

The artifact proves the rejection is an acceptance-builder defect, not runtime
accounting or ledger drift. Governed paper execution is active; four reviewed
forward entries advanced the canonical ledger from the immutable 88-row
baseline to 92 rows, with current-epoch/state rows both 4, chain and projection
parity valid, no missing rows, accounting coverage complete, zero coverage or
economic issues, and matching open symbols `AMD`, `ANET`, `LITE`, `QQQ` across
accounting/state/paper status. Self-check and daily audit pass, sentinel is
quiet/pass on exact commit `3c152d5`, risk is not halted, and equity was
`13443.10`. No halt was manually cleared and no execution was appended or
fabricated by validation.

The completed branch was `fix/issue84-poststart-evidence-forward-trades`. It keeps
the immutable 88-row/digest recovery baseline exact while validating lawful
post-start forward progress by ledger delta, current-epoch/state parity,
accounting/open-symbol reconciliation and the latest governed execution
receipt. The exact captured artifact now builds a passing read-only acceptance
bundle locally; focused tests pass 10/10, including negative regressions for
row-delta, state-row, position and receipt drift.

PR #295 exact validation head `a7c230c6e22dc9aa0e6581fa3be5ca848f3b887f`
and tree `762bb5fe3d633e15ac9326e3ff97a3c95e0df97d` passed the
repository, architecture-debt, Change Safety, refactor and Stage F workflows;
both exact Gunicorn smokes passed. It squash-merged as
`242c1221442ff7d8a457b3b6ad409895b511b379`. The same five merge-head
workflows and both Gunicorn smokes passed. Splendid settled that exact commit,
and runtime workflow `37479420953`, job `112324130755`, passed the 13/13
read-only capture and the governed evidence build. Artifact `11420448302` has
ZIP SHA-256
`332e4dc88ce728de4ba9f46902f4ca0652da7ce21e9aeb6e5d3ba4a4c6e4dafc`.
The accepted snapshot is sentinel quiet/pass on the exact merge, self-check and
daily audit pass, risk unhalted, accounting clean, and ledger chain/projection
parity valid at 93 rows / 5 current-epoch rows with no missing rows. The bundle
records every new check true and remains paper-only/read-only with
`post_start_forward_observations` as the only ongoing blocker; it neither
performed activation nor granted production authority. Next: continue Issue
#84 single-owner cutover work and collect ordinary forward lifecycle evidence
without changing the frozen #202 candidate or treating open-trade profitability
as a restart prerequisite.

## 2026-10-05 Issue #84 — governed marker wrapper repair merged; timestamp correction in progress

PR #293 exact head `125fb0bb3bcff71494ceb98d131f0b09227b7a64`
and tree `2c8e7ff1dfdbad84c217ea3dd60eca1f26cedd25` passed all
four PR workflows and both exact Gunicorn smokes, then squash-merged as
`d2fe34f659f49eb44f938860ccafd12be3436a7b`. All four merge-head code
workflows and both exact Gunicorn smokes passed. Exact Splendid deployment and
the read-only capture succeeded, but runtime job `111937564842` failed closed
while building governed evidence. Artifact `11367456069` has ZIP SHA-256
`a3245c766e95ca76d4ac80eb4a652ffcf976a5b26435e9d2df7c8721fb5e80b1`.

The artifact corrected the incident chronology: the immutable wrapper abort is
`last_discrepancy_local=2026-10-05 08:47:12 CDT`; `09:07:42 CDT` is the later
failed-recovery evaluation and halt timestamp. The PR #293 matcher bound the
incident to the latter, so it rejected the otherwise exact intent/error and
preserved the halt. The active branch is now
`fix/issue84-runtime-wrapper-incident-timestamp`; it changes only that exact
evidence-bound timestamp/reference and retains the wrapper repair and all
three immutable recovery receipts. Focused governed/transaction/journal tests
pass 52/52; exact-head Change Safety passes 21 audit-gate tests, 95 unittest
and 52 pytest cases; repository/configuration/refactor/ownership/typed-config/
debt and whitespace gates pass with zero new critical findings or warnings.
The unchanged local startup path is still limited by the recorded Yahoo rate
limits, so provider exact-head smokes remain mandatory. Next: one bounded PR,
every exact-head gate, then settled exact-main Splendid acceptance. The
validated-runtime pointer above intentionally remains PR #291.

PR #292 merged as `b03a1e34d9b8eeeb63b74caed05273bf353f6ef3`
after all PR and merge-head code gates and both exact Gunicorn smokes passed,
but settled runtime acceptance failed closed. Exact Splendid deployment and the
13/13 read-only capture succeeded; runtime workflow `37321817793` failed only
at `Build governed pre-start or post-start evidence`. Artifact `11350757633`
has ZIP SHA-256
`1a1b17f36ab505be83474bf261f7e46ba689f059d79ab78caa599f3e910914a1`.

At 2026-10-05 08:47:12 CDT a real governed entry attempt aborted before the
canonical append with `TypeError: apply.<locals>.patched_enter_position() got
an unexpected keyword argument '_governed'`, intent
`90dcbb9447ff5cbda53906411d32d0bc71e6983a097a284fecc3e5bcdee9c9c5`,
and `state_restored=true`. Canonical rows remained 88 -> 88 with unchanged
digest `f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
the account remained flat at equity `13429.13`. The runtime correctly latched
`governed pre-append abort recovery evidence drift`; governed v5 is halted and
the accepted-runtime pointer above intentionally remains PR #291. No halt was
manually cleared, and no execution was appended or fabricated.

The merged PR #293 branch was `fix/issue84-runtime-wrapper-governed-marker`. It forwards
the governed marker through all five active entry wrappers omitted from the
prior full-stack regression, extends that regression to the actual runtime
stack, and adds an exact evidence-bound successor recovery for this immutable
abort. The new recovery requires the exact intent, time, error, flat state,
unchanged ledger and both prior immutable recovery receipts; it preserves those
receipts and writes a distinct third-generation receipt. Focused governed-
restart, canonical bridge and journal tests pass 49/49. No production writer,
live or AI authority is added; strategy, sizing and hard-risk limits are
unchanged. Exact-head Change Safety passes its 21-test audit gate plus 100
unittest and 51 pytest cases; repository/configuration/refactor/ownership/
typed-configuration/debt gates pass with zero new critical findings or
warnings, and whitespace validation passes. After installing the declared
runtime dependencies in the ephemeral test image, the local exact Gunicorn
attempt was incomplete rather than passing: bootstrap remained in
`legacy_wsgi_import` after 93 seconds while Yahoo Finance rate-limited SPY,
QQQ and IWM. The two mandatory provider-hosted exact-head smoke jobs therefore
remain required.
Next: publish one bounded PR, require every exact-head gate including both
provider-hosted Gunicorn smokes, then require settled exact-main Splendid
acceptance before moving the validated-runtime pointer or claiming recovery.

## 2026-10-05 Issue #84 — immutable pre-append abort retry merged; acceptance failed closed

The next terminal-retry inspection reproduced a bounded sandbox-journal defect
on accepted main `6fb175337fefbdfca31000b99dd0ea8e31102898`. The first
pre-append recovery correctly wrote `aborted_before_append` without touching
the ledger or StateStore, but an exact retry against the same immutable previous
boundary raised an invariant error instead of returning the existing terminal
receipt. That made a safely completed pre-append abort non-idempotent across a
caller retry or process restart.

The completed branch was `fix/issue84-preappend-abort-idempotence`. An exact retry
now validates the previous ledger and StateStore boundary and returns the
existing receipt without rewriting the terminal record. Ledger-append or
StateStore drift still fails closed without mutation. The regression failed on
current main at the exact `aborted_before_append` branch before the repair;
focused tests now pass 19/19 and the wider transaction/StateStore selection
passes 57/57. Exact-head Change Safety passes 99 unittest plus 28 pytest cases;
repository/configuration/refactor/ownership/typed-config/debt gates pass with
zero new critical findings or warnings, and whitespace validation passes. The
local exact Gunicorn attempt was incomplete rather than passing: bootstrap
remained in `legacy_wsgi_import` after 93 seconds while Yahoo Finance
rate-limited SPY and QQQ. This remains sandbox-only and unregistered with no
production, runtime, order, live, AI, strategy, sizing, hard-risk or
halt-clearing authority. The settled 08:40 CDT Splendid evidence below remains
current on unchanged accepted main; no duplicate runtime research job was
started. PR #292 exact head
`81abf3536b2728192a0fc4cf3e2c13056046e6e6` and exact tree
`2440f59e804178f1d7e08205423534e470b8c9f7` passed all required PR gates and
merged as the commit recorded above. Its sandbox-only journal repair is valid,
but the unrelated active-wrapper abort means deployment acceptance is not yet
settled.

## 2026-10-05 Issue #84 — immutable ledger settlement merged and accepted

The next restart/retry inspection reproduced another bounded identity defect in
the sandbox journal. Retrying `settle_ledger` after the exact append was already
recorded returned the right phase but rewrote `updated_at`, changing the active
record bytes and SHA-256 digest. The same settled append could therefore acquire
multiple journal identities before StateStore recovery.

The completed branch was `fix/issue84-ledger-settlement-idempotence`. An exact retry
of an already `ledger_settled` record now returns the existing immutable record
without a write; the existing ledger-boundary checks still reject any drift.
Focused tests pass 17/17 and the wider transaction/StateStore selection passes
46/46. Exact-head Change Safety passes 99 unittest plus 26 pytest cases;
repository/configuration/refactor/ownership/typed-config/debt gates pass with
zero new critical findings or warnings, and whitespace validation passes. The
local exact Gunicorn attempt was incomplete rather than passing: bootstrap
remained in `legacy_wsgi_import` after 93 seconds while Yahoo Finance
rate-limited SPY and timed out QQQ. This remains sandbox-only and unregistered
with no production, runtime, order, live, AI, strategy, sizing or hard-risk
authority.

PR #291 exact head `4434ede353f5fbdc6ed3d3056f2c478692ec6efe`
and exact tree `7cb27a8d2ef7383841fd8247c2814268858995c1` passed all
four mandatory workflows and both exact Gunicorn smokes, then squash-merged as
`6fb175337fefbdfca31000b99dd0ea8e31102898`. All four merge-head code gates
and both exact Gunicorn smokes passed. Splendid accepted the exact merge and
runtime workflow `37317870438` completed a settled 13/13 read-only capture.
Artifact `11348373585` has ZIP SHA-256
`9b2976638582396e070c1e76bdfc204cfd15ab54de82a4634fe750742e745b39`.

Settled runtime evidence at 2026-10-05 08:40 CDT is pass/quiet on the exact
merge: self-check, accounting, daily audit, canonical chain, market data,
runner and risk pass; the account is flat at equity `13429.13`; the ledger
remains 88 chain-valid rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`.
Governed v5 remains active/pass, paper execution enabled and not halted. Runtime
shadow capture remains parity-only and explicitly ineligible as forward
evidence; Monday pre-open is not counted as a completed market session. The
verified-v2 failure remains nonblocking and inapplicable because the active v5
lineage supersedes it. No production writer was activated, and no `/paper/run`
call or direct order was made.

Fresh Splendid read-only evidence at 2026-10-05 08:17 CDT is pass/quiet on exact
main `ccb50d2da2eb73affddfd804130bf46135ae9cc6`: all 13 endpoints are reachable;
self-check, accounting, daily audit, canonical chain, market data, runner and
risk pass; the account is flat at equity `13429.13`; the ledger remains 88 rows
with digest `f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`.
Governed v5 is active/pass and not halted. The 15-second first capture timed out
on eight heavier endpoints while five lightweight endpoints remained reachable;
a bounded 60-second retry completed 13/13. This was latency, not an accepted
outage. Monday pre-open time is not counted as a completed forward market
session and no forward trade evidence is claimed.

## 2026-10-04 Issue #84 — immutable terminal recovery merged and accepted

The next restart/replay inspection found a bounded sandbox-journal defect after
PR #289. A repeated recovery of an already `state_committed` transaction
correctly returned `already_committed`, but it also rewrote the terminal record
with the retry timestamp. That changed the record digest and terminal bytes,
so the same completed transaction could acquire multiple terminal identities
before rollover. A focused regression reproduced the mutation exactly.

The completed branch was `fix/issue84-journal-restart-recovery`. It returns an
idempotent receipt for an exact terminal ledger/StateStore boundary without
writing the journal, and fails closed when the terminal boundary is stale or
drifted. The previously merged immutable SHA-256 terminal rollover remains
unchanged. Focused tests pass 15/15; the wider transaction/StateStore selection
passes 44/44; exact-head Change Safety passes 99 unittest plus 24 pytest cases;
repository/configuration/refactor/ownership/typed-config/debt gates pass with
zero new critical findings or warnings. The local exact Gunicorn attempt was
incomplete rather than passing: bootstrap remained in `legacy_wsgi_import`
after 93 seconds while Yahoo Finance rate-limited SPY/QQQ/IWM and IWM also
timed out. Both mandatory PR exact-head smokes subsequently passed.

PR #290 exact head `fa6f6cd64fd7183bd5a6f103cbd4b5e6267c4cd8`
and exact tree `065a1820c2f9c5a46a1ce978c0334378f4eee97b` passed all
four mandatory workflows, then squash-merged as
`ccb50d2da2eb73affddfd804130bf46135ae9cc6`. All four merge-head code gates
and both exact Gunicorn smokes passed. Splendid accepted the exact merge and
runtime workflow `37212039505` completed a settled 13/13 read-only capture.
Artifact `11307226475` has ZIP SHA-256
`19f0c4c9fe942ab0b4a6ca796028c50882ed290a4249588c01709dbdf25ae347`.

Settled runtime remains pass/quiet on the exact merge: self-check, accounting,
daily audit, canonical chain, market data, runner and risk pass; the account is
flat at equity `13429.13`; the ledger remains 88 chain-valid rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`.
Governed v5 remains active/pass, paper execution enabled and not halted. The
preserved successor lineage still surfaces the same three historical incident
checks, and verified-v2 remains a nonblocking inapplicable failure because v5
supersedes it. Sunday is not counted as a forward market session; no forward
trade evidence is claimed. This repair remains sandbox-only/unregistered and
grants no production-state, runtime, order, live, strategy, sizing, hard-risk
or AI authority. No `/paper/run` or direct order was used.

## 2026-10-03 Issue #84 — governed restart activated; forward observation pending

PR #288 exact head `dfc470251c535d0959fc571d9f754b7173dc257f`
passed all four mandatory exact-head workflows and both exact Gunicorn smokes,
then squash-merged as `73186024bd3c7b7d89bd0881e7f37b664459202f`.
All four merge-head code gates and both…36994 tokens truncated…k cutover.

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


## 2026-09-25 Issue #84 — governed v5 paper restart implementation — IN PROGRESS

The user-directed bounded paper restart is now implemented on focused branch
`fix/issue-84-governed-paper-restart` from current main
`d5c33f0021875e9f9a0d9cfa34ee8c3d9dd8c483`. The implementation is not yet
merged or deployed, so the September 25 runtime restart target is not claimed
as met and authoritative Splendid remains on the retained v5 hold/halt pending
exact-head CI, merge, deployment, and settled acceptance.

The governed transition accepts only the exact verified-flat v5 lineage, 88-row
canonical digest, projection parity, clean bidirectional accounting, flat
valuation, unchanged hard-risk baselines, and the retained Issue #222
administrative halt. It then releases only that exact validation hold/halt and
installs one process/file-locked coordinator around long/short entry,
partial-exit, and full-exit lifecycle boundaries. Durable intent receipts reject
duplicate partial exits across restart; post-execution canonical/accounting
checks halt on discrepancy. The canonical ledger now fails closed before legacy
state projection when its append fails, preventing an unledgered trade row. The
v5 accounting baseline now reconstructs from epoch starting cash rather than the
legacy $10,000 default. No canonical row or historical evidence is rewritten.

Focused regressions passed: 54 tests and 17 subtests covering exact pre-start
evidence, lineage and hard-limit preservation, long/short entry, partial/full
exit, restart persistence, duplicate rejection, canonical append failure,
projection discrepancy halt, and successor compatibility. Structural refactor
audit, architecture ownership contract, and architecture-debt regression gate
all pass against current main with no new debt; the exact diff also passes
whitespace validation. Repository validation passed and the committed exact head
implementation commit `fa881874e6a172224520118e805bdfb7a57d6107` passed the impact-aware mandatory
suite (139 tests) with exact-head Change Safety classification.

The local exact Gunicorn smoke reached the deferred bootstrap endpoint but did
not become ready inside its 90-second window. At 93.218 seconds the loader was
still alive in `legacy_wsgi_import`; four read-only benchmark downloads had
been rate-limited. This is recorded as a transient local smoke limitation, not
a pass and not a demonstrated application exception. The mandatory remote
exact-head smoke, remote CI, merge, deployment, and post-deploy acceptance
remain pending and must not be inferred from the other green local results.

No production operation occurred: the v5 hold/halt was not manually changed,
`/paper/run` was not called, immutable accounting/state/history/day-peak/recovery
evidence was untouched, and no strategy, sizing, hard-risk, live, order, or AI
authority changed. Issue #202 and the frozen `hold_10d` candidate remain
unchanged.


## 2026-09-28 Issue #84 — PR #276 reconciliation and alternate-writer repair — IN PROGRESS

The one active repair path is PR #276. Its original head
`ca341e4f404b3f2bb4ee3f2c4dace5dd1fcdbd1d` was reconciled with the preserved
local implementation commits rather than overwritten. Reconciled implementation
checkpoint `2ac89f0c914671d00392811c9c7692e35f94f273` keeps the broader exact-v5
preconditions, canonical fail-close behavior, epoch-starting-cash accounting,
restart receipts and lifecycle tests while removing the duplicate earlier
restart module.

Fresh read-only Splendid evidence before any deployment remained flat at cash
`13429.13048559457` and equity `13429.13`, with 88 chain-valid canonical rows,
digest `f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`,
projection parity, complete clean accounting and the retained Issue #222 halt/
validation hold. The runner was healthy after market close. No forward trade or
session evidence was manufactured.

The review demonstrated an additional execution defect: the surge-queue preview
reported `can_execute=true` while the risk halt was active, and both surge batch
writers could mutate positions/cash before their canonical bridge completed.
The queue now fails closed on `risk.halted`. Core entry/partial/full boundaries
and both surge batch paths statically enter the same process/file-locked
coordinator; the queue coordinator encloses its canonical bridge, verifies the
exact multi-row canonical delta and accounting/state parity, and never restores
a stale snapshot after any canonical append. Focused coverage includes retained-
halt rejection, exact two-row batch commit, the real queue-to-canonical bridge,
zero-row rollback, restart duplicate rejection and long/short partial/full
lifecycle behavior.

Focused validation passes 64 tests plus 17 subtests. Exact-checkout impact-aware
Change Safety at the implementation checkpoint passed 165 tests; repository and
Railway validation, refactor/ownership/configuration checks and architecture-
debt regression pass with zero debt growth. The Change Safety selector now
explicitly requires the governed-restart suite for these runtime paths. Remote
exact-head workflows, exact Gunicorn smoke, merge, authoritative Splendid
deployment and settled activation acceptance remain pending; the previous
incomplete provider-rate-limited smoke is still not a pass.

No production state changed, no halt or validation hold was manually cleared,
`/paper/run` was not called, and no strategy, sizing, hard-risk, live, order or
AI authority changed. Next executable step: publish this reconciled head to PR
#276, require every exact-head check-run to pass, then merge and validate the
governed status plus canonical/accounting/sentinel/self-check surfaces without
forcing a paper cycle.


## 2026-09-29 Issue #84 — reconciled PR published; exact smoke blocked — IN PROGRESS

PR #276 remains the single repair path. The complete reconciled tree at local
head `fe628473ff4b09215c9d70fa884684103584f451` passed the focused Issue #84
pytest suite (10 tests), impact-aware Change Safety (165 unittest tests plus the
10 pytest regressions), repository validation, Railway configuration
validation, refactor/ownership/configuration audits, architecture-debt/no-growth
gate, Change Safety gate self-tests (19 tests), and exact diff whitespace check.
Because this runner had no GitHub HTTPS credentials, the authenticated Git-data
API published the identical tree as fast-forward PR head
`fc17c2b7305e49928c0f424d0b8769f32be1b6ae`; no local implementation was lost.

The exact Gunicorn workflow smoke was repeated in an isolated clean checkout
after installing the declared requirements. Gunicorn listened successfully,
but `/bootstrap-status` remained `loading` in `legacy_wsgi_import` with the
loader thread alive for the full 90-second readiness window. The runner also
reported `Control server error: [Errno 1] Operation not permitted`. This is a
concrete blocking gate, not a pass. Immediately after the branch update, GitHub
reported no workflow runs for the exact head, so PR #276 remains unmerged and
undeployed.

Issue #84 comment 5890973443 records the exact branch/head, validated repairs,
smoke failure and resumable next step. No production state, canonical evidence,
halt, validation hold, strategy, hard-risk limit, live authority, order
authority or AI authority changed, and `/paper/run` was not called. Resume by
obtaining or dispatching the mandatory exact-head workflows for `fc17c2b...`,
repairing any failure on this same PR, and merging only after the exact
Gunicorn smoke and every other required gate pass; then perform settled
read-only Splendid acceptance.

GitHub then created the exact-head runs. Repository validation, architecture
debt, the full refactor/ownership/configuration/state/runtime audit, and both
remote Gunicorn smoke steps passed. Change Safety alone failed after its 165
unittest regressions because the newly required focused suite invoked
`python -m pytest` but the workflow installed only production requirements and
therefore had no pytest module. The same repair path now installs pytest as an
explicit CI-only dependency and a gate self-test pins that requirement. Local
verification passed 20 gate self-tests, all 165 unittest regressions, and all
10 focused pytest regressions. Publish this repair, then require a completely
green exact-head rerun before merge; the prior failed run is not acceptance.


## 2026-09-29 Issue #84 — governed restart active; post-start evidence repair — IN PROGRESS

PR #276 exact head `2d6f7945c5424c43771dbad3afee4692a3c7fbbd`
passed Repository Safety, Architecture Debt, the full
Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research audit,
and Change Safety, including both exact Gunicorn smokes and the newly selected
pytest regressions. It squash-merged as
`c450a9da553480cd6ea5bf2c2f93ef8bd2761e1c`; authoritative Splendid deployment
and the post-merge repository, daily-audit, refactor, Change Safety and exact
Gunicorn checks settled green.

The automatic read-only runtime capture bound the exact merge commit and reached
12/12 endpoints. It proved the governed restart `active/pass`, paper execution
enabled, validation hold false, risk halt false, post-start observations still
required, sentinel `quiet/pass` with zero incidents, self-check and daily audit
pass, flat cash/equity `13429.13048559457` / `13429.13`, 88 unchanged canonical
rows with digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`,
valid chain and projection parity, and complete clean accounting. No v5
execution row or trade exists yet; this is pre-execution lifecycle/restart/
accounting acceptance, not forward-trade evidence. No cycle was forced.

The same workflow then exposed a stale evidence-contract defect: its
pending-only cutover builder still required `validation_hold=true` and failed
after the governed release correctly set it false. A focused successor repair
now preserves the old held-state preflight path while emitting a read-only,
digest-bound post-start acceptance artifact for the exact reviewed decision,
epoch, unchanged ledger, flat accounting, released administrative controls and
active governed owner. It grants no production authority and retains
`post_start_forward_observations` as the sole remaining blocker. Local tests pass
53 cutover/canary cases, 20 Change Safety gate cases, exact replay of the
authoritative runtime artifact, and whitespace validation. Publish this repair
as the next bounded Issue #84 PR and require every exact-head gate before merge.


## 2026-09-29 Issue #84 — governed restart and post-start evidence accepted — ACTIVE TRIAL

PR #277 repaired the stale post-start evidence contract on the same bounded
Issue #84 path. Its exact head
`53bdfdbb2a659201a4ff65e17ad96b44bb2d41f3` passed Stable Paper Core v3 Stage
F, Repository Safety, Architecture Debt, Change Safety, and the full
Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research audit.
Both mandatory exact Gunicorn smoke steps passed. PR #277 squash-merged as
`9f350546382ebd5ab2326e79c14f995fef7b5d26`.

The exact-merge main workflows also passed. Splendid deployment acceptance
settled for `9f350546382ebd5ab2326e79c14f995fef7b5d26`, and the automatic read-only
runtime job reached 12/12 endpoints before successfully building and uploading
the governed post-start acceptance artifact (workflow run `36575952791`,
artifact `11038161591`, ZIP digest
`sha256:1bcd86d8db17f81bb2a2f5aa10127a41b70347c3cae48941c300128226dc1e22`).

The artifact is bound to the exact deployed commit and proves:
- governed restart `active/pass` for decision
  `issue84-governed-paper-restart-2026-09-25` and the verified-flat v5 epoch;
- paper execution enabled, validation hold released, retained administrative
  risk halt released, and hard-risk limits preserved;
- self-check and daily audit pass, sentinel `quiet/pass` with zero incidents,
  and 12/12 read-only runtime endpoints reachable;
- flat cash/equity `13429.13048559457` / `13429.13` with no positions;
- 88 immutable canonical rows, valid chain and projection parity, and unchanged
  ledger digest
  `f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`;
- complete clean accounting and no canonical/state/history/day-peak rewrite.

The accepted artifact state is `active_pending_forward_observations`; its only
blocker is `post_start_forward_observations`. Evidence digest is
`902726abbefc98db1c282647b04a7c398b24e21c819fa6192114f1dc50b5a10d` and
decision digest is
`4b154a55d2814fd9370c1f500a80e47f711acba90d03a506efc1981a23d9b415`.
The evidence builder is read-only, observed but did not perform activation, and
grants no production, order, live, strategy, sizing, or AI authority.

Issue #84's bounded governed restart is therefore implemented, merged,
deployed, and accepted as an active paper trial. Do not force a cycle or claim
forward-trade acceptance: there is still no post-start execution receipt, and
ordinary market-driven forward observations remain required. Keep Issue #202
and `hold_10d` promotion frozen under `VALIDATION_POLICY.md`; the governed
restart does not relax any performance-promotion gate.


## 2026-09-30 Issue #84 — pre-append abort recovery-forensics successor — IN PROGRESS

PR #282 exact head `ea8d9856bbbfc0f589886337195d39dd23b97226`
passed every mandatory exact-head workflow, including both exact Gunicorn
smokes, and squash-merged as
`2ff5a1201db9b50144a04e72ec587c772f583eba`. The merge-head Repository
Safety (`36762833034`), Architecture Debt (`36762833114`), Change Safety
(`36762833090`) and Refactor/runtime (`36762833109`) gates passed; Splendid
deployed that exact commit successfully.

Settled read-only runtime acceptance did not pass. The research job
`110050289773` in run `36762833109` reached all 12 monitored endpoints and
proved the exact deployed commit, 88 chain-valid canonical rows with unchanged
digest `f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`,
projection parity, zero accounting coverage/economic issues, healthy runner and
market data, and the flat account at cash `13429.13048559457` / equity
`13429.13`. It also correctly showed the system halted with one sentinel
incident and reason `governed pre-append abort recovery evidence drift`; the
evidence builder rejected acceptance. No cycle was forced.

The governed restart endpoint supplied the missing diagnosis. PR #282's
fail-closed recovery latch replaced `restart.last_discrepancy` and its original
incident timestamp with its own `not_applicable` recovery diagnostic. That
diagnostic failed exactly `exact_preappend_abort_boundary`,
`exact_incident_time`, and `exact_entry_wrapper_error`, while its no-append,
canonical digest/row/chain/parity, flat-state, accounting and hard-risk checks
all passed. Issue #84 comment `5897148822` independently preserves the original
exact incident at `2026-09-29 08:49:52 CDT`, operation `entry`, intent
`0787369dd4481d57c6d73f944f3e14cb89f3088b80ea08e8fe464d95ccac2547`,
the exact wrapper `TypeError`, 88 canonical rows before/after and
`state_restored=true`.

The single active repair branch is `fix/issue84-preserve-recovery-forensics`.
It keeps future recovery failures in separate fields without overwriting the
historical discrepancy, accepts only the complete exact deployed PR #282
failure signature as a non-destructive successor, records the independent
incident reference, and rejects near matches. It also adds
`/paper/governed-v5-restart-status` to the mandatory read-only runtime snapshot
and raises the exact settled-endpoint requirement from 12 to 13. Focused tests
currently pass 37/37. Exact-head workflows, review, merge, deployment and
settled recovery acceptance are still pending and must not be inferred from
the local result.

No canonical/accounting/state/history/day-peak evidence was rewritten, no halt
was manually cleared, `/paper/run` was not called, and no live, AI, strategy,
sizing or hard-risk authority changed. Resume by committing and publishing this
same branch, recording its exact head in Issue #84, requiring every exact-head
gate, and only then performing settled read-only Splendid acceptance.


## 2026-09-30 Issue #84 — exact recovery active; acceptance contract mismatch — IN PROGRESS

PR #283 exact head `ca2d19bf66ed4052961afa8fe5bb1eef8bbbb610`
passed all four mandatory exact-head workflows, including both exact Gunicorn
smokes, and squash-merged as
`31df5830bcab6fbba112471b7c0f38bdfe4a0788`. All merge-head code gates and
both Gunicorn smokes passed, and Splendid accepted the exact merge deployment.

The governed successor then recovered exactly and non-destructively:
`status=active`, `overall=pass`, `risk_halted=false`, recovery mode
`pr282_failed_recovery_successor`, version
`governed-v5-preappend-abort-recovery-2026-09-30-v2-pr282-successor`, all
recovery checks true, historical discrepancy preserved/not rewritten, and
incident reference `issue-84-comment-5897148822`. The canonical ledger remains
88 rows with unchanged digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`,
valid chain and state parity; the account remains flat at cash
`13429.13048559457` and equity `13429.13`. Daily audit, accounting, market data,
runner and sentinel are clean; sentinel is quiet and binds exact merge commit
`31df5830...`.

Post-merge run `36778209521` nevertheless failed only at the evidence-builder
step after its 13-endpoint read-only capture succeeded. The exact error was
`CanaryInvariantError: runtime snapshot is incomplete or unsettled`: the
builder still hard-coded the old 12-endpoint count and still read governed
status indirectly from bootstrap instead of the newly mandatory direct
endpoint. This is an acceptance-contract defect, not a recovery/runtime defect
and not settled acceptance.

The single follow-up branch `fix/issue84-recovery-acceptance-contract` updates
the builder to require 13 endpoints, consume the direct governed status, and
bind post-start acceptance to the exact recovery version/mode/independent issue
reference, preservation flags and all-true recovery checks. It adds rejection
coverage for receipt drift. No cycle was forced, no execution occurred, and no
canonical/accounting/state/history/day-peak, strategy, sizing, hard-risk, live
or AI authority changed. Resume through focused tests and every exact-head gate;
do not claim settled acceptance until the builder succeeds after deployment.


## 2026-10-01 Issue #84 — governed recovery accepted; single-owner transaction — IN PROGRESS

PR #284 exact head `00cf8bf97d6144ec706cbbc1aef4ff073c3f8a2b`
passed every mandatory workflow, including both exact Gunicorn smokes, and
squash-merged as `db196dd8423f6e27e87d7142905524c8655a62f7`.
All merge-head code gates passed. Refactor/runtime run `36779557598` completed
successfully, including settled exact-head Splendid acceptance, the 13-endpoint
read-only capture, governed evidence builder, and artifact upload.

Artifact `11126529322` has ZIP digest
`sha256:0b68af825342e9f837ca9ece1bfa398cb6444f353acdf2797d2d1bf23ee62fc3`.
It binds exact deployed commit `db196dd...`, evidence/acceptance SHA
`d189aafaeeb9d55673692cbc9e5af7cb91bdd4e0d24b907e6c8d81c02a89d9dc`,
and decision SHA
`1aa6e614d6d9cd805c07b85d6f9dd1550e158266eb86b2525f81f8636d3d40ea`.
Its state is `active_pending_forward_observations`; the only blocker is
`post_start_forward_observations`, and the builder observed rather than
performed activation. Production authority remains false.

The exact governed recovery is active/pass with risk halt and validation hold
false. Recovery version
`governed-v5-preappend-abort-recovery-2026-09-30-v2-pr282-successor`, mode
`pr282_failed_recovery_successor`, incident reference
`issue-84-comment-5897148822`, historical discrepancy preservation and every
recovery check are accepted. The account remains flat at cash
`13429.13048559457` / equity `13429.13`; canonical ledger remains 88 rows,
chain-valid and parity-clean with unchanged digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`.
Daily audit, accounting, risk, runner, market data and sentinel are pass/quiet.
Issue #84 comment `5932092317` records the durable acceptance checkpoint.

The restart recovery path is therefore settled. Forward observations remain
required evidence but are not a prerequisite for safe offline architecture
implementation. The active branch is
`fix/issue84-single-owner-transaction`. It adds a pure fail-closed transaction
that requires a typed, chain-valid canonical ledger append proof before
composing accounting projection, protected valuation, risk evaluation and
exactly one next StateStore revision. It performs no ledger append, state-file
write, runtime registration, order, live/AI action, strategy change or risk
limit change; production writer activation still requires a separately
reviewed cutover decision and settled acceptance. Focused tests currently pass
9/9. Continue through exact-diff inspection and every mandatory exact-head gate
before merge.


## 2026-10-01 Issue #84 — atomic transaction recovery journal — IN PROGRESS

PR #285 exact head `ba733c881d9f9ad76fccd3221869f6a2aa78b014`
passed every mandatory exact-head gate, including both exact Gunicorn smokes,
and squash-merged as `f7063fe2ce68a9c45c8d70cbc3f5963fa0e6e15e`.
All merge-head gates passed. Refactor/runtime run `36867526955` completed with
settled exact-deployment Splendid acceptance and artifact `11163819359` (ZIP
digest
`sha256:f07fa3a01c3060a107fe371eecff71075977199de274e06dd95c072e130767d9`).
The 13/13 read-only snapshot is PASS; sentinel is pass/quiet and binds the exact
merge commit. Governed v5 remains active/pass with paper execution enabled,
risk halt false and validation hold false. The account is flat at equity
`13429.13`; canonical ledger remains chain-valid at 88 rows with unchanged
digest
`f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166`.
Acceptance SHA is
`ea92e20adaa5ad2d07ef117aabc925bed5434e71599ad0a62b846b99ea799a11`
and decision SHA is
`207d5706e41d20c39388107ba407916c78f1e259307b676ccbb5e01456a4a4c9`.
State remains `active_pending_forward_observations`; the only blocker is
`post_start_forward_observations`, and production authority remains false.
Issue #84 comment `5932374465` is the durable settlement record.

The active functional branch is
`fix/issue84-atomic-transaction-journal`. It adds a sandbox-only, unregistered
write-ahead journal for the reviewed single-owner transaction. Recovery is
fail-closed at the immutable ledger boundary: a prepared transaction with no
append is abandoned without state mutation; an exact settled append rolls
forward exactly one bound StateStore revision; a crash after the state commit
is idempotently recognized without creating another revision. The journal is
digest-bound, process-locked, rejects unrelated ledger/state boundaries and
never rewrites a canonical ledger row. It holds no production state, order,
live or AI authority. Focused transaction/journal and audit tests currently
pass. Continue through exact-diff inspection and every mandatory exact-head
gate before merge and settled read-only deployment acceptance.

## 2026-10-22 Issue #313 — price-integrity deployment blocked; evidence exclusion in progress

PR #314 merged as `46cc50394b0c8f0ca7a439289c9ce62e18a031e5`. Its merge-head
Repository Safety run `39672181445`, Architecture Debt run `39672181507`,
Change Safety run `39672181272`, and refactor-audit job in run `39672181513`
all passed; the Change Safety exact Gunicorn smoke passed. The same refactor
run's runtime job `119473262955` failed at the mandatory settled Splendid step
after timing out for the exact merge commit. A later scheduled read-only
snapshot (`39706329925`, artifact `12395560661`, ZIP digest
`sha256:da9c580235e6ab39dd201569f5ca599ca4b6654c34dc3062e4c844c9e58cffeb`)
was operationally healthy, but did not prove exact-head deployment. A fresh
direct read of `/paper/exit-price-integrity-status` still returned v3 with the
old 0.40–2.50 envelope, not PR #314's v4 0.667–1.50 guard. Therefore PR #314
is merged but not deployed or accepted; do not close that gate from the later
generic snapshot. No cycle was forced and no halt or evidence was changed.

The active follow-up branch is `fix/issue313-suspect-outcome-exclusion`, based
on exact current main `46cc5039...`. It preserves every immutable execution and
accounting row while partitioning suspect or unverifiable exit outcomes out of
performance/ML qualification. The concrete SNOW 310.80 short entry to 528.61
exit is retained as accounting history but classified inconclusive at ratio
1.7008. ML pre-3A observed-outcome, walk-forward, readiness, and weighting gates
fail closed when such an exclusion exists. The Change Safety selector now binds
this surface to the complete performance-integrity regressions. Focused local
tests pass 36/36; broader unittest discovery ran 411 tests and was blocked only
by ten missing-environment dependencies (`pytest`, `flask`, `yfinance`), which
the mandatory workflow installs. Exact-head CI, review, merge, deployment, and
settled runtime acceptance remain pending.
## 2026-10-23 Issue #313 — deployed exact head; bounded risk-warn acceptance repair

PR #315 passed every exact-head workflow at
`236da829129ea439510258e46b7ab6748b62e3a5` and squash-merged as
`4cd3ae975795dc609d9a67c8a5a4e98edca66d93`. All merge-head code gates also
passed (`39966263493`, `39966263892`, `39966263945`, and the refactor job in
`39966264119`). Runtime job `120457491985` proved the exact Splendid deployment:
13/13 endpoints reachable, sentinel quiet/pass with zero incidents and exact
generated commit `4cd3ae9...`, self-check pass, 141-row chain-valid canonical
ledger with clean projection parity and 53 current-epoch rows, accounting zero
coverage/economic issues, and a flat account at equity `12952.06`. Artifact
`12507716442` has ZIP digest
`sha256:78a8f76b2f0bf6bd741628dd559e012899dbca5b3586fcaaf79681362c7a692f`.

Settled governed acceptance nevertheless failed only at `daily_audit_pass`.
The daily audit was `warn` because the non-halting risk status reported 1.478%
intraday drawdown; risk halt was false, self-defense was clear, runner and
market data passed, the provider circuit was closed, and there were zero
unclassified requests. This is an acceptance-contract mismatch, not a code
deployment, accounting, ledger, price-integrity or runtime failure.

Branch `fix/issue313-safe-risk-warn-acceptance` narrowly permits `warn` only
for that bounded safe combination. Any audit failure, risk halt, self-defense,
runner error, market-data warning, open provider circuit or unclassified
request remains fail closed; every existing sentinel, exact-commit,
accounting, ledger, projection, epoch, recovery and hard-risk condition remains
unchanged. Thirty-five focused artifact and Change Safety tests pass. Replaying
the exact merge-head artifact now emits governed post-start acceptance with
`daily_audit_safe=true`; the only blocker is the already-established
`post_start_forward_observations`. Exact-head CI, review, merge, redeployment
and settled runtime acceptance are still required before Issue #313 is closed.

Issue #316 holds the separate scorecard checkpoint at remote branch
`feat/daily-performance-scorecard-20261023`, exact head
`c77a34efe655e98be779c99cfd2e895fa4a1187a`; resume it only after this repair
is accepted.

## 2026-10-23 Issues #313/#316 — exact deployment proven; risk-warn acceptance repair required

PR #315 exact head `236da829129ea439510258e46b7ab6748b62e3a5`
passed Repository Safety (`39792816332`), Architecture Debt
(`39792816400`), Change Safety including the exact Gunicorn smoke
(`39792816367`), and the refactor audit (`39792816285`). It squash-merged as
`4cd3ae975795dc609d9a67c8a5a4e98edca66d93`. All four merge-head code
workflows also passed (`39966263493`, `39966263892`, `39966263945`, and the
refactor job in `39966264119`).

The merge-head runtime job `120457491985` then proved the exact Splendid
deployment: 13/13 endpoints were reachable, sentinel was quiet/pass with zero
incidents and exact generated commit `4cd3ae9...`, self-check passed, the
141-row canonical ledger was chain-valid and projection-clean at 53 current
epoch rows, accounting had zero coverage/economic issues, and the account was
flat at equity `12952.06`. Artifact `12507716442` has ZIP digest
`sha256:78a8f76b2f0bf6bd741628dd559e012899dbca5b3586fcaaf79681362c7a692f`.
However, governed acceptance correctly remains open: the daily audit was
`warn` solely because risk reported a non-halting 1.478% intraday drawdown;
market data and runner passed, risk was not halted, and self-defense was clear.
The acceptance builder still required literal `daily_audit.overall=pass` and
failed `daily_audit_pass`. Repair that bounded acceptance-contract mismatch
without weakening any accounting, ledger, halt, sentinel, hard-risk or
deployment requirement, then repeat every exact-head gate and settled runtime
acceptance. Do not describe PR #315 as fully accepted before that succeeds.

Issue #316 owns the separate daily performance scorecard. The specialist's
bounded 2026-10-22 observation proves 4 entries, 3 final exits and 3 completed
matched lifecycles with matched realized P/L `-109.40`: PANW long `-0.62`, FPS
short `-75.68`, and TTMI short `-33.10`; MOD short remained open. The missing
session-close account snapshot means canonical daily P/L, unrealized P/L,
equity, exposure, fees and slippage are unknown, so the observation is
explicitly non-comparable and rolling 5/20 samples remain zero. The standalone
read-only scorecard builder preserves prior observations on correction, never
mutates source rows, does not infer P/L from balance changes, and keeps suspect
fills canonical while excluding them from eligible research. Fifty-eight
focused scorecard, Change Safety and performance-integrity regressions pass
locally. The one-variable `risk_off` short-admission cap is recorded only as a
hypothesis with full VALIDATION_POLICY gates; it has not started and is not a
promotion. Branch `feat/daily-performance-scorecard-20261023` is the durable
checkpoint; hold it behind the Issue #313 acceptance repair before PR review.

## 2026-10-24 Issues #313/#316 — correctness accepted; scorecard merged; one-variable research bounded

Issue #313 is settled at exact deployed main
`9b1e78622be5279a2aacbf4c97c07485e5f77d01`. Repository Safety
`39968447911`, Architecture Debt `39968447769`, Change Safety
`39968447858`, Stage F `39968447642`, and refactor audit
`39968447865` all passed; both exact Gunicorn smokes passed. Splendid and
runtime job `120465167617` passed. Runtime artifact `12508412973` has digest
`sha256:2b3d340cb336112a3df301cf29c10a29bb58d06ba469eab4ef90c1579f922d8c`.
It proves 13/13 endpoints, exact sentinel commit `9b1e786...`, sentinel
pass/quiet with zero incidents, self-check pass, 141 chain-valid canonical rows
with clean projection parity and 53 current-epoch rows, zero accounting
coverage/economic issues, no risk halt, and flat equity `12952.06`. The
bounded non-halting 1.478% risk warning now passes only through
`daily_audit_safe=true`; every accounting, ledger, halt, runner, market-data,
sentinel and exact-commit gate remained true. Governed state is
`active_pending_forward_observations`, with only
`post_start_forward_observations` remaining. No immutable evidence, strategy,
sizing, hard-risk limit, live or AI authority changed.

Daily scorecard PR #318 exact head
`5c5835355e660377bf1056333b8b2b5401f26a02` passed every exact-head PR gate,
including both Gunicorn smokes, and squash-merged as
`f3417292c633ecc65ae39942faf254f9997d5e84`. Every merge-head code gate also
passed, including both exact Gunicorn smokes. Refactor/runtime run
`40100655913` completed successfully with settled exact-head Splendid
acceptance; runtime artifact `12563001313` has digest
`sha256:b70aa70943ccf24a20f751691713b9af61a5942366cf52692fba2d246f0ba50a`.
The scorecard is read-only and keeps 2026-10-22 explicitly
incomplete/non-comparable: four entries, three
final exits, three matched lifecycles and matched realized P/L `-109.40`;
MOD remained open and no provable session-close account, equity, exposure or
cost snapshot exists. Rolling comparable 5/20 samples remain zero.

The single performance specialist then evaluated the predeclared one-variable
candidate: cap new `risk_off` short lifecycles at one per session while
holding ranker, sizing, exits and cost model constant. The result is
`insufficient_evidence`, not improvement: zero complete comparable same-epoch
sessions; no exact ordered `risk_off` admission rows with net-after-cost
outcomes; unknown fees/slippage; no research/holdout partitions; and absent
sample, duration, regime, concentration, stress, walk-forward and forward-shadow
gates. The Oct. 22 FPS+TTMI combined `-108.78` after MOD is hypothesis
motivation only. Branch `research/issue316-risk-off-short-cap-20261024` adds a
fail-closed, isolated static-admission evaluator, focused tests and a dated
evidence record; it never synthesizes fills or changes runner authority.
Validate its exact diff and all exact-head gates before review. The next
executable performance step is to repair/collect the specifically missing
ordered admission plus net-after-cost source coverage, then rerun the same
predeclared baseline/candidate without retuning.


## 2026-10-26 Issue #321 — fail-closed session evidence adapter — IN PROGRESS

Exact accepted main at session start is
`a5f42663dda1ef73e05fb8c7a080cf09043f5db6`; no competing PR was open. The
prior completed market session remains Friday 2026-10-23 and is already
preserved by the merged scorecard. Monday activity is in progress and is not a
completed-session scorecard.

The bounded source audit proves the exact missing coverage rather than assuming
more observations will solve it. Existing trade-journal snapshots are bounded
timestamped observations, not session-close receipts: they have no close
window contract, direct epoch identity, canonical daily P/L, persisted gross
exposure or cost coverage. Canonical plus state-primary execution rows can
prove gross executed lifecycles and execution order, but there is no exact
fees/slippage ledger and no complete durable ordered rule-admission universe.
Latest-cycle scanner rows remain insufficient for all-day causation. The
`risk_off` cap experiment therefore remains `insufficient_evidence`; no policy
or promotion state changed.

Branch `fix/session-performance-evidence-adapter` adds a pure archived-JSON
adapter. It verifies the complete canonical hash chain, requires one-to-one
execution-ID joins to state-primary journal rows, enforces Chicago session and
accounting epoch, groups partial and final exits into one lifecycle, exposes a
close observation only inside a declared window, preserves suspect paths while
excluding them from eligible research, and refuses net-after-cost output unless
every joined execution has explicit fees and slippage. It labels the only
currently provable ordering as `executed_admission_order_only`, declares the
complete entry universe unavailable, and cannot promote a candidate. It does
not import the runner or write runtime/accounting/history state. Twelve focused
adapter and scorecard regressions plus compile and exact-diff checks pass
locally. Mandatory exact-head CI, review, merge, deployment and settled
acceptance remain pending.

Next executable step: publish the focused Issue #321 PR, run every exact-head
gate including the exact Gunicorn smoke, and merge/deploy only if all required
checks pass. After acceptance, use a digest-bound archived artifact as adapter
input; missing close or cost sources must remain explicit rather than inferred.


## 2026-10-28 Issues #324/#325 — emergency broker/runtime stabilization checkpoint

All strategy features, ML promotion, performance optimization and optional
architecture work are frozen. Exact current main is
`92c23ed45ea9abcf074956bb37d326239de47768`. PR #323 was closed unmerged as
nonessential; its evidence branch remains preserved.

Read-only runtime evidence collected 09:00–09:03 CDT proves both Railway
services deploy the same code but are independent internal simulation writers
to separate volumes. Clean is `dazzling-dedication / Clean / Trading-bot`,
state `/data/state.json`; Splendid is
`splendid-creativity / production / web`, state `/app/data/state.json`.
Both internal auto-runners are enabled at 300-second intervals. Clean is flat
at equity/cash `-26064.31`, halted, daily-audit FAIL, with 193 accounting
coverage issues and 18 canonical current-epoch executions missing from the
mutable state projection; its canonical ledger is not authoritative for new
executions. Clean's latest internal execution is
`e746b3e674654f9199402c8904df1f43` at 2026-08-14T13:51:07Z. Splendid is
flat at equity/cash `12879.85`; sentinel, audit, accounting, canonical chain
and projection, risk, runner and market data pass. Its ledger is authoritative
for internal executions. Splendid's latest execution is
`9c87c9a3f3d44fb4ad8729cc078fee85`, a PLTR short exit at
2026-10-27T15:03:18Z.

Exact-SHA source inspection proves the deployed application is an internal
simulator: the entry/exit functions only update internal portfolio state and
append internal execution rows. Current runtime source has no Alpaca SDK
import/client, broker REST endpoint, or submit/place/create-order call path.
The Alpaca dependency is declared but unused by runtime code; no other tracked
broker integration was found. The retired GitHub paper runner is manual-only
and performs no HTTP request. Consequently neither current Railway runtime can
be identified as the source of the user-observed Alpaca PAPER positions from
the available evidence. Those six broker positions do not match either flat
runtime.

Broker identity remains the blocking gap: neither runtime exposes a broker
account fingerprint, broker positions/open orders or broker order/client IDs,
and the connected Alpaca surface is market-data-only. Do not compare broker
and internal P/L, claim a single brokerage writer, or stop Clean. Obtain
read-only Alpaca PAPER account fingerprint (non-secret hash), positions, open
orders, recent order IDs/client IDs/timestamps and fills, then match them
one-to-one to journal/execution IDs or list explicit exceptions. Until then the
brokerage writer is unassigned and blocked. The proposed internal single-writer
boundary is Splendid; Clean remains evidence-only/consolidation-candidate, but
both continue internal cycles today.

Acceptance before any Clean compute stop: prove PAPER endpoint and non-secret
account identity; match broker orders/fills/positions against named ownership;
separate broker from simulation reporting; recheck SHA, risk, accounting,
ledger and runner; prove no other credential consumer/order writer; measure the
Railway monthly cost baseline and savings; preserve/export Clean deployment
configuration; retain its volume; and prove rollback can reattach the volume.
Only then propose an operator-reviewed Clean compute stop and duplicate
auto-deploy disable. Never delete the project/volume or rotate credentials as
a blind first action.

One route named `/paper/runtime-controls-repair-status` unexpectedly performs
an atomic rewrite of `runtime_controls.json`. It was called once on each
service while inspecting permission boundaries. Both calls reported successful
rewrites with no trading action, no canonical/history edit, and no strategy,
threshold, sizing, risk, live or ML authority change. It is not an
observational endpoint and must not be called again for evidence capture. No
`/paper/run`, EOD report, reset, close-all, service, volume, credential,
halt-clear or broker action was performed.

Issue #324 comment 6471095866 holds the detailed map and acceptance checklist.
Issue #325 comment 6471096281 records milestone accountability: 34 days remain
to the 2026-12-01 hard review. Next executable step is direct read-only Alpaca
PAPER account/order/position evidence and exact order-to-execution matching.

## 2026-10-29 Issues #324/#325 — Alpaca screenshot reconciliation narrows ownership gap

Emergency stabilization remains the only objective; no strategy, ML, research,
merge, deployment, service, credential, volume or automation change was made.
Exact repository main and both runtime deployments remain
`92c23ed45ea9abcf074956bb37d326239de47768`.

Three user-supplied Alpaca screenshots were inspected as read-only broker
evidence. `IMG_2415.png`
(`sha256:7f2a8eddbdec4eff4a4e4f97bb602ddea794982188b9146813c6db826d48a283`)
explicitly says Paper Trading and shows the Open-orders filter with zero rows.
`IMG_2413.png` and `IMG_2414.png`
(`sha256:35656864fe80795757d0239ad24d710d5198aecf6b9a7a5038d1306a1e12ab2f`
and
`sha256:ff0a72cc85cfaad9aed51b3df9ad764afda0921468a3e5b7d763cee79364238a`)
show the same separate broker context: current equity `169719.66`, cash
`45969.45`, long market value `123936.11`, short market value `-185.90`
and last-close equity `169712.09`. No account number or credential was
captured or recorded. The user separately reports that Alpaca shows no trades
after 2026-04-22. This is useful first-party attestation, but the screenshots
do not expose the all-orders export, order/client IDs, fills or a non-secret
account fingerprint, so the exact broker writer remains unassigned.

The 09:01–09:06 CDT read-only runtime refresh strengthens separation rather
than proving broker ownership. Clean is still flat at `-26064.31`, halted,
with its 300-second runner active but entry-blocked; its audit still fails with
193 coverage issues, 18 state-projection omissions and a non-authoritative
current ledger. Its latest internal execution remains
`e746b3e674654f9199402c8904df1f43`. Splendid is flat at `12876.37`,
with its 300-second runner active and capable of new internal entries. Its
audit passes: 159 chain-valid ledger rows, 71 current-epoch rows, zero
accounting coverage/economic issues and exact state parity. Since the prior
checkpoint it added 18 internal execution rows; the latest is
`72f24a8d09f4426c938b5fb6892d0bdd`, a RIOT long
`market_regime_protection` exit. The broker screenshots and user-reported
2026-04-22 last-trade boundary therefore do not match these current internal
execution IDs. At this exact SHA, the tracked runtime has no broker submit
path, so these are internal-simulation executions, not evidence of Alpaca
orders.

Current safe boundary: Splendid is the sole proposed owner of the internal
simulation ledger; Clean is a halted evidence-preservation/consolidation
candidate. This is not yet an accepted single broker writer. Clean still runs
read-only/blocked cycles, Splendid still writes internal simulation evidence,
and an external Alpaca API consumer cannot be excluded until read-only broker
order history and connected-client evidence are obtained. Do not stop Clean,
disable auto-deploy, rotate keys or compare broker/internal P/L yet.

Acceptance remains fail closed:

1. Export/read the Alpaca PAPER all-orders and fills history with immutable
   order ID, client order ID, status and timestamps; derive only a non-secret
   account fingerprint.
2. Match every broker position and fill to a named writer and internal
   execution ID, or record an explicit exception; separately prove zero open
   broker orders.
3. Confirm no other API-key consumer or broker integration can submit orders.
4. Recheck exact deploy SHA, risk, accounting, canonical chain/projection and
   runner state for both runtimes.
5. Capture the Railway monthly cost baseline and expected Clean savings;
   export Clean deployment/volume attachment configuration and prove rollback.
6. Only after 1–5 pass, submit an operator-reviewed proposal to stop Clean
   compute while retaining its volume and disabling duplicate auto-deploy.

There are 33 days to the 2026-12-01 hard review. The next executable step is
the read-only Alpaca PAPER all-orders/fills export plus connected API-client
inventory. If that cannot be obtained through the current tools, the exact
user-only action is to export those records from Alpaca without changing or
revoking credentials; no pause or consolidation is claimed.

## 2026-10-30 Issues #324/#325 — paper endpoint and account fingerprint bound, key ownership still open

Emergency stabilization remains the only objective. Exact repository main and
both deployments are still
`92c23ed45ea9abcf074956bb37d326239de47768`; no merge, deployment,
service, runner, credential, volume, halt, strategy, ML, research or
automation mutation was performed.

Two new user-supplied screenshots add a non-secret broker identity and
dependency boundary without exposing credentials. Alpaca profile screenshot
`IMG_2420.png`
(`sha256:d12f0803f3033b09e22f16e57bf6962676759969213fdfeeb176902ea7987ee7`)
shows a distinct Paper Account whose identifier is recorded only as the
one-way, truncated fingerprint `sha256:9870d64de4a2fa5e`; its paper API
endpoint is `https://paper-api.alpaca.markets/v2`. The same page separately
shows Alpaca's live endpoint, but no live-account identity or live order
evidence was captured. Railway Clean screenshot `IMG_2421.png`
(`sha256:3d0c68e6e0d281260e30a670c53623cef48ae01f9c438439bc7f48f6307fd47a`)
shows `ALPACA_BASE_URL` configured to the paper endpoint family and masked
Alpaca key variables plus an `AUTO_TRADING` variable. No secret value was
read, copied or recorded.

This proves Clean is configured with paper-broker credentials and a paper
endpoint, but it does **not** prove those masked keys belong to the displayed
paper account and does not prove Clean submitted any order. Current exact-SHA
source still has no runtime Alpaca client or broker-submit path, and both
deployment-info surfaces declare `places_orders=false`. A focused repository
history check cannot resolve the 2026-04-22 ownership boundary because the
available Git history begins on 2026-09-08; no April deployment/source commit
is present locally to inspect. Historical Clean ownership therefore remains an
explicit exception, not an inference.

Read-only runtime observations at 08:49–08:57 CDT remain unchanged in all
material identity fields. Clean is flat at `-26064.31`, halted and
entry-blocked while its 300-second runner continues; latest internal execution
is still `e746b3e674654f9199402c8904df1f43`. Splendid is flat at
`12876.37`, not halted, with its 300-second runner capable of internal
entries; latest internal execution remains
`72f24a8d09f4426c938b5fb6892d0bdd`. There are no new internal executions
since the 2026-10-29 checkpoint. The prior exact-SHA accounting/ledger audit
remains reusable because deploy SHA and execution boundaries are unchanged:
Clean failed with 193 coverage issues and 18 state-projection omissions;
Splendid passed with 159 chain-valid rows, 71 current-epoch rows, zero
coverage/economic issues and exact projection parity.

Single-writer boundary remains proposed, not accepted: Splendid is the sole
intended internal-simulation writer; Clean is a halted
evidence-preservation/consolidation candidate. Broker ownership remains
unassigned because the paper account fingerprint is not cryptographically
bound to Clean's masked keys and there is no all-orders/fills export or API
client inventory. Do not stop Clean, disable auto-deploy, rotate keys or
compare broker/internal P/L.

Acceptance checklist remains fail closed:

1. Obtain read-only PAPER account/order/fill data using the account fingerprint
   above; capture immutable order ID, client order ID, status and timestamps.
2. Bind the masked Clean credential set to the fingerprint without revealing
   secrets, then match every fill and current position to a named writer and
   internal execution ID or an explicit exception.
3. Obtain an Alpaca connected-client/key-usage inventory or equivalent audit
   proving no other submitter, and independently confirm zero open orders.
4. Recheck both runtime SHAs and risk/accounting/ledger/runner state.
5. Measure Railway monthly cost, export Clean configuration/volume attachment,
   and prove retained-volume rollback before any stop proposal.

There are 32 days to the 2026-12-01 hard review. Next executable step is a
read-only Alpaca PAPER API account/orders/fills call using already configured
credentials through an approved, non-logging path, or an Alpaca-generated
order/activity statement if API access cannot be safely exposed. No broker
pause or consolidation is claimed.

## 2026-10-31 Issues #324/#325 — April source recovered; historical broker writer still unassigned

Emergency stabilization remains the only objective. Repository `main`, Clean,
and Splendid all remain at exact SHA
`92c23ed45ea9abcf074956bb37d326239de47768`. No merge, deployment,
service, runner, credential, volume, halt, strategy, ML, research or automation
mutation was performed.

GitHub's remote commit collection resolves the prior local-history limitation:
ten repository commits from 2026-04-22 through 2026-04-23 were retrieved and
their exact `app.py` blobs inspected. The latest is
`03bc3413ef740253e2e8df1338bec0353cffd979` at
2026-04-23T02:48:27Z; the sequence includes
`de8da15ede5729a2c39e7cf98d3a7eec7cbf3ecc` through that commit.
None of the ten files contains an Alpaca import/client, broker endpoint,
`submit_order`, `create_order`, `place_order`, APCA credential use or other
broker-submit call. The latest tree contains only `Procfile`, `app.py`,
`requirements.txt` and `runtime.txt`; `app.py` imports yfinance and mutates an
in-memory `portfolio`, while `alpaca-trade-api` is only an unused dependency in
`requirements.txt`. Its exposed routes are internal dashboard/status/metrics
surfaces. This strongly excludes the repository code visible for the reported
2026-04-22 broker activity as an Alpaca writer.

That is source evidence, not historical deployment evidence: no Railway
deployment record currently binds Clean's 2026-04-22 running deployment to one
of those exact commits, and no Alpaca all-orders/client-order-ID export is
available. Therefore historical broker ownership remains unassigned; manual
orders, another service, or another API-key consumer remain explicit possible
exceptions. Do not infer Clean placed the Alpaca orders merely because its
current environment has masked Alpaca variables.

Read-only runtime observations at 09:01–09:03 CDT show both deployments still
declare `places_orders=false` and the same exact SHA. Clean remains flat at
`-26064.31`, halted and entry-blocked; its latest internal execution remains
`e746b3e674654f9199402c8904df1f43`. Splendid is now an active internal
simulation context with one DELL short position, equity `12897.85`, cash
`12243.665477`, and unrealized P/L `6.90`. Its Oct 30 internal cycle added
ALAB/DELL/COHR entries and exits/partial exits; the retained DELL path begins
with entry `73a529ef23804cfba4d3fb32922158d2` and partial exit
`adcbcd3d48424d4ca5a0ef326eb447f6`. These are internal ledger IDs, not
broker order IDs. Weekend runner attempts correctly skipped because the market
was closed.

Because Splendid's execution boundary changed, its compact daily audit was
rerun read-only. It passes with 166 chain-valid ledger rows, 78 current-epoch
rows, exact state projection parity, zero accounting coverage/economic issues,
and a reconstructed open DELL position matching state. Clean's prior audit was
not redundantly rerun because its SHA and execution boundary remain unchanged;
its recorded 193 coverage issues and 18 projection omissions still apply.

The ownership boundary remains proposed, not accepted: Splendid is the sole
intended internal-simulation writer; Clean is a halted evidence-preservation
candidate; the Alpaca PAPER writer is unassigned. Independent paper-order
generation cannot be ruled out until the configured Clean key is bound to the
non-secret paper-account fingerprint and the Alpaca all-orders/fills plus
key/client-usage inventory are reconciled.

Acceptance remains fail closed:

1. Obtain a read-only Alpaca PAPER all-orders/fills export with immutable order
   ID, client order ID, status and timestamps; independently confirm open-order
   count.
2. Bind Clean's masked key set to `sha256:9870d64de4a2fa5e` without revealing
   secrets, then match each broker fill/position to a named writer/internal ID
   or an explicit exception.
3. Obtain historical Railway deployment evidence for 2026-04-22 and an Alpaca
   key/client-usage inventory; prove no other submitter can act.
4. Recheck both runtime SHAs and risk/accounting/ledger/runner state at the
   consolidation decision boundary.
5. Measure Railway monthly cost, export Clean configuration/volume attachment,
   and prove retained-volume rollback before any stop proposal.

There are 31 days to the 2026-12-01 hard review. The next executable step is
the Alpaca-generated PAPER order/activity statement plus historical Railway
deployment record and key-usage/client inventory. If unintentional paper-order
generation cannot be excluded, the operator-controlled pause remains: identify
the actual submitter first, capture pre-state, pause only that submitter with
its documented control, and verify no new broker orders; no pause is claimed.
