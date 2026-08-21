# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-21 11:06 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Current `main`: `69ec3d39a565a8c9068d0a088f441723e6883c3e` (`Update handoff for current-chat continuity and clean-epoch provenance (#100)`)  
Active provenance PR: #101, branch `agent/verified-snapshot-provenance-20260821`  
Canonical Railway paper service: `https://trading-bot-clean.up.railway.app`

## Communication / Continuity Rule

Keep Trading-bot progress communication in the **currently active ChatGPT project conversation**. This is not permanently tied to one thread. When the project intentionally moves to a new ChatGPT conversation, update this handoff first and treat the new conversation as the active project chat.

Project-specific monitoring tasks that could post into stale chats remain disabled unless a future active project conversation intentionally re-establishes them. Repository handoff maintenance is mandatory so a new conversation can recover exact state without relying on prior-chat memory.

When the active conversation is becoming too large for reliable continuation, warn the user **before** a testing/update sequence is started, finish or stop at a clean boundary, refresh this handoff with all material evidence and the exact next action, then move conversations. Do not force a chat switch in the middle of an avoidable test sequence.

## Executive Status

Operational stabilization is still blocked by Issue #82. Runtime remains paper-only. Rules remain sole execution authority. Live authority is disabled. ML/AI remains shadow-only for execution.

The fresh-day protection is now correctly fail-closed, but the authoritative paper account snapshot is corrupted and cannot seed a new risk day. Current live/on-disk state is approximately:
- `cash=-26064.308325`
- `equity=-26064.31`
- no open positions
- `realized_total=-94929.16`

Risk remains stale from 2026-08-20:
- `day_start_equity=-26064.31`
- `day_peak_equity=0.01`
- `halted=true`
- `halt_reason='daily loss limit hit (3.0%)'`
- `fresh_day_reset_pending=true`

Do not clear the halt, rewrite the risk peak, force a baseline, rewrite/relabel canonical ledger rows, or overwrite the account from an incomplete reconstruction merely to make an audit pass.

## Current Runtime Evidence — 2026-08-21

### Fresh-day guard

`/paper/fresh-day-check`:
- `baseline_status=pending`
- risk date still `2026-08-20`
- `day_start_equity=-26064.31`
- `day_peak_equity=0.01`
- `fresh_day_reset_pending=true`
- `halted=true`

`/paper/fresh-risk-day-baseline-guard-status`:
- installed / overall pass
- `current_equity_sane=false`
- start/peak both not sane
- `fresh_day_reset_pending=true`
- prospective only; no halt clear/current-day rewrite/peak rewrite/history edit/order/strategy/sizing/threshold/live/ML authority change

Interpretation: PR #83/#87 protection is functioning and refusing to manufacture a 2026-08-21 risk baseline from invalid equity.

### Compact self-check

`/paper/self-check` at 09:51 CDT:
- overall `warn`, status `ok`
- account cash/equity `-26064.31`, no positions, realized total `-94929.16`
- auto runner healthy; no active runner error
- all 9 bounded component checks pass
- scanner/entry ownership and runtime shadow parity pass
- entries remain blocked by the stale risk halt

### Full daily audit

`/paper/daily-audit?full=1` at 09:52 CDT:
- overall `fail` because risk is halted and accounting is unreconciled
- runner and market-data/provider accounting pass
- persistent volume healthy; in-memory/on-disk richness matched
- accounting reconstruction estimates `cash/equity=10724.779592`, `realized_total=724.779592`, zero positions
- reconstruction coverage is incomplete: 193 ignored/unmatched legacy exit rows, beginning 2026-08-07
- separate ledger-economic integrity also fails

Therefore `$10,724.779592` is forensic evidence only and **must not be promoted automatically into authoritative state**.

### Canonical execution ledger

`/paper/canonical-execution-ledger-status`:
- status/overall pass
- append-only/hash-chain enabled
- hook applied; authoritative for new executions
- `chain_valid=true`, no parse/hash errors
- `row_count=55`
- `current_epoch_id=legacy-pre-stable-core`
- `current_epoch_rows=55`
- last execution id `e746b3e674654f9199402c8904df1f43`

The ledger is healthy and immutable. Do not edit/relabel these rows. The active runtime no longer exposes `stable-paper-v2-20260812-verified01`.

### Clean accounting epoch status

`/paper/clean-accounting-epoch-status`:
- `status=blocked`, `overall=warn`
- `marker_status=null`
- `forensic_archive_dir=null`
- `historical_recovery_decision=null`
- `historical_evidence_archived=false`
- `clean_start=false`
- `zero_trade_baseline=false`
- `validation_hold=false`

The endpoint's displayed `epoch_id=stable-paper-v1-20260810-clean01` is a target constant when inactive, not proof of an active clean epoch. Active clean metadata/marker is absent from this status path.

### State recovery guard — decisive current-startup evidence

`/paper/state-recovery-status` at approximately 10:54 CDT:
- `restored=false`
- `pre_restore_backup_file=null`
- current state valid, score 39, 303 trades, 0 positions, 500 history rows
- largest backup valid, score 39, 280 trades, 19 positions, 500 history rows
- decision `should_restore=false`
- reason `backup_has_fewer_trades_than_current`
- current runner timestamp rank is materially newer than the largest backup
- monotonic trade and runner timestamp guards enabled

Interpretation: `state_guard` did **not** resurrect the old snapshot during this startup. Restoring `state_backup_largest.json` would roll execution history backward and is prohibited.

### State I/O hardening — latest evidence

`/paper/state-io-status` at 10:59 CDT:
- installed / status ok
- `last_status_event=atomic_save_state`
- current state valid with 303 trades, 0 positions, 500 history rows
- `state.json` about 25.8 MB
- latest/prewrite backups about 25.4 MB; largest backup about 38.3 MB
- atomic writes, retry reads, backup fallback reads, thread/file locking, and non-overlapping cycle protections are enabled
- run state inactive at snapshot, no run error, zero overlap blocks

Interpretation: there is no evidence in the **current** State I/O status of a fallback backup read; the latest recorded event is a normal atomic save. This status does not preserve a complete historical event log, so it cannot by itself prove that no fallback read ever occurred before PR #98. Combined with `state_guard.restored=false`, the corrupted `/data/state.json` existed before the current startup recovery decision. The pre-PR #98 X-Ray independent state I/O remains the leading known resurrection mechanism, but final provenance still needs durable marker/archive evidence.

## PR #101 — Read-only verified-snapshot provenance probe

PR #101 was opened from main specifically to answer the remaining provenance question without touching paper state.

Head at PR creation: `62edf2d4f74259b1a728e7d06a8387638a2c1755` before the handoff refresh commit.

It adds `/paper/verified-snapshot-provenance-status` with these boundaries:
- reads only exact small clean/verified recovery marker files, bounded forensic archive manifests, and the already-loaded in-memory portfolio;
- does **not** read the 25–38 MB state/backup files;
- does not import or call either one-shot recovery implementation;
- no file writes, backup restore, state repair, halt clear, ledger rewrite/relabel, order placement, strategy/sizing/risk-threshold/live/ML change;
- bounded archive directory scan and bounded returned matches;
- focused regression added to Change Safety Audit while preserving the mandatory core invariant suite.

Do not merge #101 unless exact-head Change Safety Audit, repository validation, architecture debt/ownership/config checks, focused provenance tests, and exact Gunicorn startup smoke are green.

## Issue #82 — Stabilization Exit Gate

Issue #82 remains open and authoritative.

Prospective protections already merged:
- #56 source terminal-price plausibility guard
- #79 fresh cached quote provenance/plausibility
- #80 catastrophic persisted `last_price` fallback guard
- #81 pre-mutation duplicate full-exit guard
- #83 fresh-day baseline sanity guard
- #87 fresh-day guard installed before full WSGI composition
- #98 diagnostic X-Ray independent authoritative state I/O removed

Remaining acceptance:
1. authoritative economic state recovered from mechanically proven provenance, not inference;
2. sane fresh-day risk initialization from protected positive valuation;
3. one normal forward paper market session after clean reset;
4. evidence-based historical-accounting disposition without rewriting immutable execution history;
5. clean active audit with sane valuation, healthy runner/market data, valid canonical chain, no new active economic/coverage issue, and risk reflecting real economics.

Current fresh-day status is `pending`, which is the correct fail-closed state while authoritative equity is invalid.

## This Week's Reliability / Architecture / Governance Changes

### 2026-08-18
- #79 merged — validate fresh cached quotes before `latest_price` return.
- #80 merged — fail closed on catastrophic persisted `last_price` valuation fallback.
- #81 merged — block duplicate full exits at canonical pre-mutation boundary; historical TEM evidence remains immutable.

### 2026-08-19
- #83 merged — prospective fresh-risk-day baseline sanity guard.
- Issue #84 opened — Stable Paper Core v3 consolidation.
- #85 merged — Stage A immutable canonical shadow state models/ownership contract.

### 2026-08-20
- #86 merged — compact observational `/paper/fresh-day-check`.
- #87 merged — install fresh-day guard before full WSGI composition; Gunicorn smoke passed.
- #88 merged — master system audit + architecture-debt regression gate. Audit baseline: 250 Python files / 90,409 lines; 34 runtime mutation overlaps; 5 env conflicts; 5 route overlaps; 80 duplicate-function groups; 540 broad exception-pass sites; 8 watchdog loops; 32 critical findings; fragmented ownership included `save_state` 17, `scan_signals` 14, `try_entries_and_rotations` 13, `entry_quality_check` 10, `enter_position` 9.
- #89 merged — Stage B deterministic shadow valuation.
- #90 merged — Stage C deterministic shadow risk lifecycle.
- #91 merged — Stage D shadow canonical StateStore.
- #92 merged — Stage E shadow ledger-derived bidirectional accounting.

### 2026-08-21
- #93 merged — Stage F shadow canary-readiness planner; no authoritative cutover.
- Issue #94 created — mandatory per-change regression/impact auditing.
- #95 merged — exact-head Change Safety Audit with core invariants, impact-aware tests, architecture/config/ownership/debt checks, and exact startup smoke.
- Issue #96 created — self-diagnosing incident triage/recommendation engine.
- #97 merged — shadow-only `system_sentinel` foundation; no production mutation/self-healing authority.
- #98 merged as `c6ef7958a247ae88ba9a5c3670ed756ac0d06426` — `entry_pipeline_xray` no longer loads/saves authoritative state or reassigns `core.portfolio`; regression proves stale-file/live-memory split cannot replace live state. Required CI passed and Railway deployed.
- #99 merged as `0874368ad5bf303337b8c94ed1c9ae967c2231b5` — authoritative handoff refresh.
- #100 merged as `69ec3d39a565a8c9068d0a088f441723e6883c3e` — current-chat continuity + clean-epoch provenance handoff update.
- #101 open — bounded read-only durable recovery provenance probe and focused Change Safety regression selection.

## Stable Paper Core v3 / Issue #84

Issue #84 remains open. Shadow/parity stages:
- A #85 — immutable state models
- B #89 — deterministic valuation
- C #90 — deterministic risk
- D #91 — shadow StateStore
- E #92 — ledger/accounting projection
- F #93 — canary readiness only
- G — blocked until authoritative cutover/parity/prospective evidence

Do not use shadow core to bypass Issue #82.

## Mandatory Change Safety / Issue #94

PR #95 implemented the in-repository exact-head audit. Every relevant PR must pass Change Safety Audit plus overlapping regressions and the mandatory core suite. Missing/stale/failing evidence blocks merge. PR #101 additionally routes verified-snapshot provenance changes to their focused regression, demonstrating the intended impact-aware model instead of indiscriminately expanding all tests.

Final post-rebuild completion still includes repository-rule/branch-protection enforcement where permissions support it and acceptance/closure of Issue #94.

## Self-Diagnosing Sentinel / Issue #96

PR #97 provides the shadow diagnostic foundation across valuation, accounting, ledger, risk, startup, configuration, ownership, runner, and market-data boundaries. It may recommend bounded fixes and select affected tests, but must not rewrite state, clear halts, alter execution history, change strategy/sizing/hard-risk/live/ML authority, or auto-merge authoritative repairs.

## Prior Verified Accounting Recovery — Forensic Evidence Only

Existing recovery code documents the previously verified Aug. 12 recovery design:
- old epoch `stable-paper-v1-20260810-clean01`
- target `stable-paper-v2-20260812-verified01`
- decision `verified-bad-tick-and-ledger-divergence-2026-08-12`
- exact LRCX bad execution id `5ca38922916e4612ae3cda8d9801107d`
- expected recovery marker path under the persistent state directory: `verified_snapshot_verified-bad-tick-and-ledger-divergence-2026-08-12.json`
- forensic archives under `/data/forensic_archives` with `verified_snapshot_recovery_manifest.json`

Do **not** call `verified_snapshot_epoch_recovery.status_payload()` as a diagnostic route: in the legacy module it delegates to `apply()`, which is the one-shot recovery entry point. PR #101's provenance probe intentionally avoids importing/calling that module.

## Historical TEM Duplicate Exit

Immutable TEM evidence:
1. long entry `29.640567 @ 54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`;
2. first full exit `29.640567 @ 53.105`, execution `7b13d9194a23407f926667b2f48d4057`;
3. duplicate full exit `@ 52.905`, execution `3530dbf965db4894ba93b7098cec3696`.

PR #81 prospectively prevents recurrence. Never delete/rewrite/fabricate/relabel the historical row.

## Canonical Runtime / Validation Links

Use only the clean service:
- bootstrap: `https://trading-bot-clean.up.railway.app/bootstrap-status`
- compact fresh-day: `https://trading-bot-clean.up.railway.app/paper/fresh-day-check`
- fresh-day guard: `https://trading-bot-clean.up.railway.app/paper/fresh-risk-day-baseline-guard-status`
- self-check: `https://trading-bot-clean.up.railway.app/paper/self-check`
- full diagnostics: `https://trading-bot-clean.up.railway.app/paper/full-self-check`
- full daily audit: `https://trading-bot-clean.up.railway.app/paper/daily-audit?full=1`
- canonical ledger: `https://trading-bot-clean.up.railway.app/paper/canonical-execution-ledger-status`
- clean epoch: `https://trading-bot-clean.up.railway.app/paper/clean-accounting-epoch-status`
- state recovery: `https://trading-bot-clean.up.railway.app/paper/state-recovery-status`
- state I/O: `https://trading-bot-clean.up.railway.app/paper/state-io-status`
- verified snapshot provenance after #101 deploy: `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-provenance-status`
- quote/exit integrity: `https://trading-bot-clean.up.railway.app/paper/exit-price-integrity-status`

Do not manually call `/paper/run` unless a future validation plan explicitly requires it.

Known ops debt: `.github/workflows/refactor-audit.yml` still contains the older `https://web-production-e1796.up.railway.app` runtime-research target. Do not treat that old-domain snapshot as clean-service acceptance evidence.

## Risk / Authority Boundaries — Preserve

- soft daily-loss pause 1.0%
- hard realized-loss halt 2.5%
- hard intraday drawdown halt 2.5%
- absolute daily-loss ceiling 3.0%
- max configured account risk per trade at stop 2.0%
- terminal-price plausibility 0.40x minimum / 2.50x maximum
- paper-only until explicit live-readiness approval
- rules sole execution authority
- ML shadow-only for execution
- no historical ledger fabrication/deletion/rewrite/relabel
- no manual state repair merely to pass an audit

## Exact Next Action

1. Re-fetch PR #101 exact head and CI after this handoff commit.
2. Inspect the exact PR diff for accidental write/recovery authority.
3. Merge only if Change Safety Audit, focused provenance regression, repository safety, architecture debt/ownership/config, and exact Gunicorn startup smoke all pass at the exact head.
4. Wait for Railway to deploy the merge and settle to `delegate_ready:true`.
5. Run only `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-provenance-status`.
6. If the exact verified marker or matching forensic manifest survives, use that mechanically proven durable evidence to design the bounded successor recovery without rewriting the 55-row canonical ledger.
7. If neither survives, do not guess. Build the next bounded read-only discriminator for recovery metadata in specific backups/archive inventory without promoting the incomplete `$10,724.779592` reconstruction.
8. After proven authoritative recovery, require sane fresh-day reset, forward paper session, and clean active audit before Issue #82 closure or Stage F/G authority.

## Conversation Continuity Protocol

Stay in the current active project chat through a coherent testing/update sequence. The assistant cannot rely on a UI meter, so it must use conversation size/complexity judgment and proactively warn the user before continuation becomes unsafe. When a move is needed, stop at a clean boundary, refresh this handoff, then use:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Treat this conversation as the current active project chat and keep project-status communication here. Verify current main/PR/CI and the canonical Railway clean-service read-only evidence before changing code. Continue from the Exact Next Action. Preserve paper-only authority, hard risk thresholds, canonical ledger history, rules-only execution authority, ML shadow-only execution, and the Issue #82/#84/#94/#96 gates. Do not manually repair account state or clear halts from inference.
```
