# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-21 12:15 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Current `main`: `45b83dfca905aef4b2e51f30a0fb2ec7480f53f1` (`Add read-only verified snapshot provenance probe (#101)`)  
Active PR: #102 `agent/verified-snapshot-backup-provenance-20260821`  
Canonical Railway paper service: `https://trading-bot-clean.up.railway.app`

## Communication / Continuity Rule

Keep Trading-bot progress communication in the **currently active ChatGPT project conversation**. This is not permanently tied to one thread. When the project intentionally moves to a new conversation, refresh this handoff first and treat the new conversation as the active project chat.

Project-specific monitoring tasks that could post into stale chats remain disabled unless a future active project conversation intentionally re-establishes them. Repository handoff maintenance is mandatory so a new conversation can recover exact state without relying on prior-chat memory.

When the active conversation is becoming too large for reliable continuation, warn the user **before** starting another test/update sequence, finish or stop at a clean boundary, refresh this handoff with all material evidence and the exact next action, then move conversations. Do not force a chat switch in the middle of an avoidable test sequence.

## Executive Status

Operational stabilization is still blocked by Issue #82. Runtime remains paper-only. Rules remain sole execution authority. Live authority is disabled. ML/AI remains shadow-only for execution.

The fresh-day protection is correctly failing closed, but the authoritative paper account snapshot is corrupted and cannot seed a new risk day. Current live/on-disk state remains approximately:
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

Do not clear the halt, rewrite the risk peak, force a fresh-day baseline, rewrite/relabel canonical ledger rows, restore an older backup, or overwrite the account from an incomplete reconstruction merely to make an audit pass.

## Current Runtime Evidence — 2026-08-21

### Fresh-day guard

`/paper/fresh-day-check`:
- `baseline_status=pending`
- risk date remains `2026-08-20`
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

Interpretation: PR #83/#87 protection is functioning and refusing to manufacture a 2026-08-21 baseline from invalid equity.

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
- reconstruction coverage is incomplete: 193 ignored/unmatched legacy exit rows beginning 2026-08-07
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

The endpoint's displayed `epoch_id=stable-paper-v1-20260810-clean01` is a target constant when inactive, not proof of an active clean epoch.

### State recovery guard

`/paper/state-recovery-status` at approximately 10:54 CDT:
- `restored=false`
- `pre_restore_backup_file=null`
- current state valid, score 39, 303 trades, 0 positions, 500 history rows
- largest backup valid, score 39, 280 trades, 19 positions, 500 history rows
- decision `should_restore=false`
- reason `backup_has_fewer_trades_than_current`
- current runner timestamp is newer than largest backup
- monotonic trade and runner-timestamp guards enabled

Interpretation: `state_guard` did **not** resurrect the old snapshot during this startup. Restoring `state_backup_largest.json` would roll history backward and is prohibited.

### State I/O hardening

`/paper/state-io-status` at 10:59 CDT:
- installed / status ok
- `last_status_event=atomic_save_state`
- current state valid with 303 trades, 0 positions, 500 history rows
- `state.json` about 25.8 MB
- latest/prewrite backups about 25.4 MB; largest backup about 38.3 MB
- atomic writes, retry reads, backup fallback reads, thread/file locking, and non-overlapping cycle protections enabled
- run state inactive at snapshot, no run error, zero overlap blocks

Interpretation: current State I/O does not show a backup fallback read; the latest recorded event is normal atomic persistence. This does not prove no fallback read occurred historically, but combined with `state_guard.restored=false` it proves the corrupted `state.json` existed before the current startup recovery decision.

### PR #101 verified-snapshot marker/archive provenance result

PR #101 merged to main as `45b83dfca905aef4b2e51f30a0fb2ec7480f53f1`. Exact-head Change Safety Audit, focused provenance regression, repository validation, architecture debt/ownership/config checks, and exact Gunicorn startup smoke passed before merge.

`/paper/verified-snapshot-provenance-status` at 12:06 CDT returned:
- `active_runtime.accounting_epoch_id=null`
- `active_runtime.paper_accounting_epoch_id=null`
- active cash/equity remain `-26064.31`, 303 trades, 0 positions
- `clean_epoch_marker_found=false`
- expected clean marker path `/data/clean_epoch_journal-recovery-incomplete-2026-08-10.json` does not exist
- `verified_snapshot_marker_found=false`
- expected verified marker path `/data/verified_snapshot_verified-bad-tick-and-ledger-divergence-2026-08-12.json` does not exist
- `verified_snapshot_archive_found=false`
- `/data/forensic_archives` itself does not exist
- `durable_verified_evidence_found=false`
- diagnosis `recovery_markers_and_verified_archive_not_found`
- endpoint confirms reporting-only/no-write/no-restore/no-ledger-rewrite authority

Interpretation: the dedicated Aug. 10/Aug. 12 recovery marker and forensic archive evidence is no longer present on the current Railway volume. This removes the simplest mechanically proven recovery source. Do not infer authoritative account values from memory or the incomplete reconstruction.

## PR #102 — Read-only retained-backup provenance discriminator

PR #102 is the next bounded discriminator. It adds `/paper/verified-snapshot-backup-provenance-status` and is **diagnostic only**.

It will:
- stream the four known retained state backups: `state.json.bak`, `state_backup_latest.json`, `state_backup_prewrite.json`, `state_backup_largest.json`;
- never load an entire large backup JSON into memory;
- read the small `state_snapshots/manifest.json` without pruning/deleting anything;
- scan at most three retained snapshots that look recovery-era by tiny trade count or Aug. 12 timestamp;
- bound per-file and cumulative bytes read;
- extract only the exact `paper_accounting_epoch` JSON object with brace/string-aware bounded parsing;
- require the full verified signature before treating a backup as authoritative provenance: epoch `stable-paper-v2-20260812-verified01`, decision `verified-bad-tick-and-ledger-divergence-2026-08-12`, baseline type `verified_snapshot_with_open_position`, recovery disposition `verified_snapshot_rollforward`, archived-history flag true, and prior epoch `stable-paper-v1-20260810-clean01`;
- keep startup `apply()` constant-time; large backup scans occur only when the explicit route is requested;
- perform no orders, state writes, backup restores, snapshot deletion/pruning, halt clears, ledger rewrites/relabels, or strategy/sizing/threshold/live/ML changes.

Do not merge #102 unless its **final exact head** passes the mandatory Change Safety Audit, both provenance regressions, core Stable Paper invariants, repository safety, architecture ownership/config/debt checks, and exact Gunicorn startup smoke.

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

Current fresh-day status remains `pending`, which is the correct fail-closed state while authoritative equity is invalid.

## This Week's Reliability / Architecture / Governance Changes

### 2026-08-18
- #79 merged — validate fresh cached quotes before `latest_price` return; poisoned-cache regression added.
- #80 merged — fail closed on catastrophic persisted `last_price` valuation fallback.
- #81 merged — block duplicate full exits at canonical pre-mutation boundary; historical TEM evidence remains immutable.

### 2026-08-19
- #83 merged — prospective fresh-risk-day baseline sanity guard.
- Issue #84 opened — Stable Paper Core v3 consolidation.
- #85 merged — Stage A immutable canonical shadow state models/ownership contract.

### 2026-08-20
- #86 merged — compact observational `/paper/fresh-day-check`.
- #87 merged — install fresh-day guard before full WSGI composition; exact Gunicorn smoke passed.
- #88 merged — master system audit + architecture-debt regression gate. Audit baseline: 250 Python files / 90,409 lines; 34 runtime mutation overlaps; 5 env conflicts; 5 route overlaps; 80 duplicate-function groups; 540 broad exception-pass sites; 8 watchdog loops; 32 critical findings; fragmented ownership included `save_state` 17, `scan_signals` 14, `try_entries_and_rotations` 13, `entry_quality_check` 10, `enter_position` 9.
- #89 merged — Stage B deterministic shadow valuation.
- #90 merged — Stage C deterministic shadow risk lifecycle.
- #91 merged — Stage D shadow canonical StateStore.
- #92 merged — Stage E shadow ledger-derived bidirectional accounting.

### 2026-08-21
- #93 merged — Stage F shadow canary-readiness planner; no authoritative cutover.
- Issue #94 created — mandatory per-change regression/impact auditing.
- #95 merged — exact-head Change Safety Audit with mandatory core invariants, impact-aware tests, architecture/config/ownership/debt checks, and exact startup smoke.
- Issue #96 created — self-diagnosing incident triage/recommendation engine.
- #97 merged — shadow-only `system_sentinel` foundation; no production mutation/self-healing authority.
- #98 merged as `c6ef7958a247ae88ba9a5c3670ed756ac0d06426` — `entry_pipeline_xray` no longer loads/saves authoritative state or reassigns `core.portfolio`; exact regression proves stale-file/live-memory split cannot replace live state. Required CI passed and Railway deployed.
- #99 merged as `0874368ad5bf303337b8c94ed1c9ae967c2231b5` — authoritative handoff refresh through Aug. 21.
- #100 merged as `69ec3d39a565a8c9068d0a088f441723e6883c3e` — current-chat continuity + clean-epoch provenance handoff update.
- #101 merged as `45b83dfca905aef4b2e51f30a0fb2ec7480f53f1` — bounded marker/archive verified-snapshot provenance probe; production evidence found no surviving marker/archive root.
- #102 open — bounded retained-backup/snapshot provenance probe; no mutation authority.

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

PR #95 implemented the in-repository exact-head audit. Every relevant PR must pass Change Safety Audit plus overlapping regressions and the mandatory core suite. Missing/stale/failing evidence blocks merge.

PR #101 added focused verified-snapshot provenance regression selection. PR #102 extends that focused set to the retained-backup provenance regression while preserving all mandatory core tests.

Final post-rebuild completion still includes repository-rule/branch-protection enforcement where permissions support it and acceptance/closure of Issue #94.

## Self-Diagnosing Sentinel / Issue #96

PR #97 provides the shadow diagnostic foundation across valuation, accounting, ledger, risk, startup, configuration, ownership, runner, and market-data boundaries. It may recommend bounded fixes and select affected tests, but must not rewrite state, clear halts, alter execution history, change strategy/sizing/hard-risk/live/ML authority, or auto-merge authoritative repairs.

## Prior Verified Accounting Recovery — Forensic Facts Only

Existing recovery code documents the previously verified Aug. 12 recovery design:
- old epoch `stable-paper-v1-20260810-clean01`
- target `stable-paper-v2-20260812-verified01`
- decision `verified-bad-tick-and-ledger-divergence-2026-08-12`
- exact LRCX bad execution id `5ca38922916e4612ae3cda8d9801107d`
- expected marker `verified_snapshot_verified-bad-tick-and-ledger-divergence-2026-08-12.json`
- expected forensic archive root `/data/forensic_archives`
- recovery code wrote the recovered state to `state.json`, state I/O latest/largest/prewrite backups, and `state.json.bak`, then reset the bounded snapshot archive with the recovered zero-trade state.

The current dedicated marker/archive files are absent. PR #102 therefore checks only whether any retained backup or recovery-like snapshot still contains the **exact full epoch object**. Do not call `verified_snapshot_epoch_recovery.status_payload()` as a diagnostic route: in the legacy module it delegates to `apply()`, the one-shot recovery entry point.

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
- verified marker/archive provenance: `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-provenance-status`
- verified backup provenance after #102 deploy: `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-backup-provenance-status`
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

1. Re-fetch PR #102 exact final head after this handoff commit.
2. Inspect the exact diff for accidental write/restore/prune/recovery authority and confirm startup does not scan large backups.
3. Merge only if Change Safety Audit, both provenance regressions, core invariants, repository safety, architecture ownership/config/debt, and exact Gunicorn bootstrap smoke pass on that exact head.
4. Wait for Railway to deploy and settle to `delegate_ready:true`.
5. Run only `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-backup-provenance-status`.
6. If a backup/snapshot contains the full verified epoch signature, use that mechanically proven source to design a bounded successor recovery that preserves all 55 canonical ledger rows/hash chain and archives the current contaminated state first.
7. If no full verified signature survives, do not guess. The next discriminator must remain read-only and target remaining durable evidence sources (for example journal/snapshot metadata) before any authoritative recovery design.
8. After proven authoritative recovery, require sane fresh-day reset, one normal forward paper session, and a clean active audit before Issue #82 closure or Stage F/G authority.

## Conversation Continuity Protocol

Stay in the current active project chat through a coherent testing/update sequence. The assistant cannot rely on a UI context meter, so it must use conversation size/complexity judgment and proactively warn the user before continuation becomes unsafe. When a move is needed, stop at a clean boundary, refresh this handoff, then use:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Treat this conversation as the current active project chat and keep project-status communication here. Verify current main/PR/CI and the canonical Railway clean-service read-only evidence before changing code. Continue from the Exact Next Action. Preserve paper-only authority, hard risk thresholds, canonical ledger history, rules-only execution authority, ML shadow-only execution, and the Issue #82/#84/#94/#96 gates. Do not manually repair account state or clear halts from inference.
```
