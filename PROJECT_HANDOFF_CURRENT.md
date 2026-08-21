# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-21 12:58 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Current `main`: `78bddaf5ea6e3a6fc8b6e102f47c77a8b4955dad` (`Add read-only backup provenance status`, PR #102)  
Active PR: #103 `agent/verified-snapshot-journal-ledger-provenance-20260821`  
Canonical Railway paper service: `https://trading-bot-clean.up.railway.app`

## Communication / Continuity Rule

Keep Trading-bot progress communication in the **currently active ChatGPT project conversation**. It is not permanently tied to one thread. When the project intentionally moves to a new conversation, refresh this handoff first and treat the new conversation as the active project chat.

Project-specific monitoring tasks that could post into stale chats remain disabled unless a future active project conversation intentionally re-establishes them. When the current conversation is becoming too large for reliable continuation, warn the user **before** starting another testing/update sequence, stop at a clean boundary, refresh this file with all material evidence and the exact next action, then move chats. Do not force a switch mid-test when avoidable.

## Executive Status

Issue #82 remains the operational stabilization gate. Runtime is paper-only; rules remain sole execution authority; live authority is disabled; ML/AI execution remains shadow-only.

The prospective fresh-day guard is correctly failing closed, but the authoritative paper account snapshot is corrupted and cannot seed a new risk day:
- cash `-26064.308324919723`
- equity `-26064.31`
- zero open positions
- realized total `-94929.16`
- stale risk day start `-26064.31`
- stale risk peak `0.01`
- halt `daily loss limit hit (3.0%)`
- fresh-day reset pending

Do **not** clear the halt, rewrite the risk peak, force a baseline, restore an older state backup, rewrite/relabel canonical ledger rows, or overwrite the account from the incomplete `$10,724.779592` reconstruction just to make an audit pass.

## Current Runtime Evidence — 2026-08-21

### Fresh-day / self-check

`/paper/fresh-day-check` remains pending on the 2026-08-20 risk state. `/paper/fresh-risk-day-baseline-guard-status` is installed/pass but reports current equity, day start, and day peak as not sane; the guard is correctly refusing the reset.

`/paper/self-check` at 09:51 CDT:
- account cash/equity `-26064.31`, no positions, realized total `-94929.16`
- runner healthy; no active runner error
- all nine bounded component checks pass
- scanner/entry ownership and runtime shadow parity pass
- entries blocked by stale risk halt

### Full daily audit

`/paper/daily-audit?full=1` at 09:52 CDT:
- overall fail because risk is halted and accounting is unreconciled
- runner and market-data/provider accounting pass
- persistent volume healthy; in-memory/on-disk richness match
- legacy state-trade reconstruction estimates cash/equity `10724.779592`, realized total `724.779592`, zero positions
- reconstruction coverage is incomplete with 193 ignored/unmatched legacy exits beginning 2026-08-07
- separate ledger economic integrity also fails

`10724.779592` is forensic evidence only and is not an authoritative recovery value.

### Canonical execution ledger

`/paper/canonical-execution-ledger-status`:
- append-only/hash-chain enabled
- authoritative hook applied for new executions
- `chain_valid=true`
- no parse/hash errors
- `row_count=55`
- all 55 currently report epoch `legacy-pre-stable-core`
- last execution id `e746b3e674654f9199402c8904df1f43`

The ledger remains immutable. Never edit/relabel these rows to manufacture epoch continuity.

### Clean epoch / persistence / recovery

`/paper/clean-accounting-epoch-status` is blocked/warn with no active completion marker, no forensic archive dir, no historical recovery disposition, `clean_start=false`, and `zero_trade_baseline=false`. The displayed v1 epoch id is a target constant when inactive, not active-epoch proof.

`/paper/state-recovery-status`:
- `restored=false`
- current state 303 trades / 0 positions
- largest backup 280 trades / 19 positions
- decision `should_restore=false`, reason `backup_has_fewer_trades_than_current`

Therefore startup recovery did not resurrect the current state on this boot and restoring `state_backup_largest.json` is prohibited.

`/paper/state-io-status`:
- latest event `atomic_save_state`
- current state valid structurally with 303 trades / 0 positions
- no current evidence of a fallback backup read

The corrupted snapshot now persists normally; the known pre-PR #98 X-Ray independent state I/O remains the leading proven mechanism capable of replacing a newer live state with stale persisted state.

### PR #101 — marker/archive provenance

PR #101 merged as `45b83dfca905aef4b2e51f30a0fb2ec7480f53f1` after exact-head Change Safety Audit, focused provenance tests, repo safety, architecture/config/debt checks, and Gunicorn startup smoke passed.

`/paper/verified-snapshot-provenance-status` at 12:06 CDT:
- active accounting epoch ids null
- clean recovery marker missing
- verified Aug. 12 recovery marker missing
- `/data/forensic_archives` missing
- no matching verified manifest
- `durable_verified_evidence_found=false`
- diagnosis `recovery_markers_and_verified_archive_not_found`

### PR #102 — retained backup/snapshot provenance

PR #102 merged as `78bddaf5ea6e3a6fc8b6e102f47c77a8b4955dad`. Its exact PR head passed Change Safety Audit, all focused provenance/core regressions, repository safety, architecture ownership/config/debt checks, and exact Gunicorn bootstrap smoke before merge. Both Railway deployment contexts later reported success.

`/paper/verified-snapshot-backup-provenance-status` at 12:46 CDT is decisive:
- diagnosis `verified_snapshot_not_found_in_retained_backup_or_targeted_snapshot_set`
- `verified_snapshot_backup_evidence_found=false`
- no verified signature path
- no clean signature path
- no verified token-only path
- `state.json.bak`, `state_backup_latest.json`, `state_backup_prewrite.json`, and `state_backup_largest.json` all contain only `legacy-pre-stable-core` epoch ids and no `paper_accounting_epoch` object / verified decision / verified baseline / bad-execution token
- largest backup is the Aug. 10 38.3 MB / 280-trade snapshot and still has no clean or verified epoch object
- snapshot manifest retains eight periodic checkpoints, all 303-trade / zero-position snapshots from Aug. 20–21
- no recovery-era or zero-trade snapshot remains to inspect
- 113,860,712 bytes were streamed read-only; no whole-state load, write, restore, prune, or ledger mutation occurred

Conclusion: **no current Railway state backup or retained state snapshot preserves the Aug. 12 verified epoch.** Do not restore any current backup.

## Durable GitHub Evidence of the Prior Verified Recovery

Although current Railway recovery artifacts are gone, merged GitHub history independently proves the verified v2 recovery was not merely planned:

- PR #45 merged as `9b659c88f77d5004e82ee0dda8e6d26c074621e8` on Aug. 12. Its exact-signature recovery reversed the proven LRCX `36.26` bad-tick mutation, restored the remaining `3.42486` LRCX shares at `312.90` basis, and started `stable-paper-v2-20260812-verified01` under validation hold. The recovery constants deterministically yield cash `10768.497730982748` and starting equity `11885.824057382748` at verified LRCX mark `326.24`.
- PR #46 merged as `16c4c2371e46d23d15057f172a37756ff5245342` after a Railway bootstrap hang **following PR #45**; it fixed the recovery journal-lock deadlock without changing recovery arithmetic or authority.
- PR #48 merged as `b5ea9d9192f7ac7cf65d8e342d11727ac3249b2b` and explicitly describes the v1→v2 verified snapshot migration as successful. It accepted only the exact successor relationship: active v2, prior v1, `verified_snapshot_rollforward`, archived historical evidence.
- PR #52 merged as `d82f6eb327c90dede362fc0160167ac8c18c327f`; its rationale says the canonical execution ledger was already authoritative for `stable-paper-v2-20260812-verified01` and fixed compact reporting to use the persisted active successor epoch.

These are durable historical facts, but they still do not by themselves prove that every one of the **current** 55 immutable canonical rows belongs downstream of that cutover. That temporal link is the purpose of PR #103.

## PR #103 — Journal/Ledger Temporal Provenance

PR #103 is a read-only Issue #82 discriminator. It adds `/paper/verified-snapshot-journal-ledger-provenance-status`.

The verified recovery wrote top-level `accounting_epoch_id=stable-paper-v2-20260812-verified01` and `verified_snapshot_epoch_started_local` into both trade-journal files. Normal journal mirroring starts from the existing journal object and preserves unknown top-level keys, so those markers may have survived even though state markers/backups did not.

The #103 route:
- scans only root-level selected trade-journal scalar keys using bounded streaming reads so nested historical tokens cannot falsely prove provenance;
- line-streams the current canonical JSONL and independently verifies the same previous-hash/event-hash chain semantics;
- reports epoch histogram, first/last execution ids, first/last ledger timestamps, and whether every parseable current ledger row is at/after the verified journal cutover time;
- never syncs/seeds the journal, writes files, restores state, edits/relabels ledger rows, clears a halt, places orders, or changes strategy/sizing/risk/live/ML authority;
- performs no journal or ledger scans during startup; reads occur only on explicit route access.

Do not merge #103 unless its final exact head passes Change Safety Audit, all three provenance regressions, mandatory Stable Paper Core invariants, repository safety, architecture ownership/config/debt checks, and exact Gunicorn bootstrap smoke.

## Issue #82 — Stabilization Exit Gate

Prospective protections already merged:
- #56 source terminal-price plausibility
- #79 fresh cached quote provenance/plausibility
- #80 catastrophic persisted `last_price` valuation fallback guard
- #81 pre-mutation duplicate full-exit guard
- #83 fresh-day baseline sanity guard
- #87 pre-WSGI fresh-day installation order
- #98 removal of diagnostic X-Ray authoritative state I/O

Still required:
1. recover authoritative economics from mechanically defensible provenance, not inference;
2. sane positive fresh-day risk initialization;
3. one normal forward paper market session after recovery;
4. evidence-based historical-accounting disposition without rewriting immutable executions;
5. clean active audit with sane valuation, healthy runner/market data, valid canonical chain, no new active economic/coverage issue, and risk reflecting real economics.

Current fresh-day state remains correctly pending while authoritative equity is invalid.

## This Week's Reliability / Architecture / Governance Changes

### Aug. 18
- #79 cached-quote validation
- #80 persisted-mark valuation fail-closed guard
- #81 canonical pre-mutation duplicate full-exit guard

### Aug. 19
- #83 fresh-risk-day baseline sanity guard
- Issue #84 opened — Stable Paper Core v3
- #85 Stage A immutable shadow state models

### Aug. 20
- #86 compact `/paper/fresh-day-check`
- #87 pre-WSGI guard ordering fix
- #88 master system audit + architecture-debt freeze. Audit baseline: 250 Python files / 90,409 lines; 34 mutation overlaps; 5 env conflicts; 5 route overlaps; 80 duplicate-function groups; 540 broad exception-pass sites; 8 watchdog loops; 32 critical findings; fragmented owners included `save_state` 17, `scan_signals` 14, `try_entries_and_rotations` 13, `entry_quality_check` 10, `enter_position` 9.
- #89 Stage B deterministic shadow valuation
- #90 Stage C deterministic shadow risk
- #91 Stage D shadow StateStore
- #92 Stage E shadow ledger/accounting projection

### Aug. 21
- #93 Stage F shadow canary-readiness only
- Issue #94 mandatory per-change regression/impact auditing
- #95 exact-head Change Safety Audit gate
- Issue #96 self-diagnosing triage/recommendation engine
- #97 shadow-only `system_sentinel`
- #98 X-Ray stale-file/live-memory overwrite repair, merge `c6ef7958a247ae88ba9a5c3670ed756ac0d06426`
- #99 handoff refresh, merge `0874368ad5bf303337b8c94ed1c9ae967c2231b5`
- #100 current-chat continuity/clean-epoch handoff, merge `69ec3d39a565a8c9068d0a088f441723e6883c3e`
- #101 marker/archive provenance probe, merge `45b83dfca905aef4b2e51f30a0fb2ec7480f53f1`
- #102 retained-backup provenance probe, merge `78bddaf5ea6e3a6fc8b6e102f47c77a8b4955dad`; runtime result found no surviving verified backup/snapshot
- #103 open — journal/ledger temporal provenance probe

## Stable Paper Core v3 / Issue #84

Shadow/parity stages:
- A #85 immutable state
- B #89 valuation
- C #90 risk
- D #91 StateStore
- E #92 accounting projection
- F #93 canary readiness only
- G blocked until #82 authoritative recovery/parity/prospective evidence

Do not use shadow core to bypass #82.

## Mandatory Change Safety / Issue #94

PR #95 established the in-repository exact-head audit. Every relevant PR must pass overlapping regressions plus the mandatory core suite; stale/missing/failing evidence blocks merge. #101 added verified-marker provenance selection, #102 added retained-backup provenance, and #103 extends the focused set to journal/ledger provenance.

Repository branch protection is not currently enabled on `main`, so final post-rebuild governance still includes repository-rule enforcement where permissions support it. The in-repo audit policy remains mandatory regardless.

## Self-Diagnosing Sentinel / Issue #96

#97 is advisory/shadow only across valuation, accounting, ledger, risk, startup, config/ownership, runner, and market-data boundaries. It may classify incidents and recommend bounded tests/fixes but must not rewrite state, clear halts, edit execution history, change strategy/sizing/hard-risk/live/ML authority, or auto-merge authoritative repairs.

## Historical TEM Duplicate Exit

Immutable TEM evidence:
1. entry `29.640567 @ 54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`
2. first full exit `29.640567 @ 53.105`, execution `7b13d9194a23407f926667b2f48d4057`
3. duplicate full exit `@ 52.905`, execution `3530dbf965db4894ba93b7098cec3696`

#81 prospectively prevents recurrence. Never delete/rewrite/fabricate/relabel the historical row.

## Known CI / Ops Debt

The post-#102 `daily-operational-audit` status is red because three older test expectations are stale, not because #102 provenance behavior failed: one expects recursion to win next-action precedence over section 10b, one expects a curated test fixture to be `pass` rather than `warn`, and one looks for the obsolete literal bootstrap version token `v6-registration-heartbeat`. Keep this cleanup separate from the active accounting-provenance sequence unless it becomes a required gate.

`.github/workflows/refactor-audit.yml` still contains the old `https://web-production-e1796.up.railway.app` research target. Do not use that old-domain runtime artifact as clean-service acceptance evidence.

## Canonical Runtime / Validation Links

Use only the clean service:
- bootstrap: `https://trading-bot-clean.up.railway.app/bootstrap-status`
- fresh-day: `https://trading-bot-clean.up.railway.app/paper/fresh-day-check`
- fresh-day guard: `https://trading-bot-clean.up.railway.app/paper/fresh-risk-day-baseline-guard-status`
- self-check: `https://trading-bot-clean.up.railway.app/paper/self-check`
- full audit: `https://trading-bot-clean.up.railway.app/paper/daily-audit?full=1`
- canonical ledger: `https://trading-bot-clean.up.railway.app/paper/canonical-execution-ledger-status`
- state recovery: `https://trading-bot-clean.up.railway.app/paper/state-recovery-status`
- state I/O: `https://trading-bot-clean.up.railway.app/paper/state-io-status`
- marker/archive provenance: `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-provenance-status`
- backup provenance: `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-backup-provenance-status`
- journal/ledger provenance after #103 deploy: `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-journal-ledger-provenance-status`

Never manually call `/paper/run` unless a future validation plan explicitly requires it.

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
- no manual account/risk repair merely to pass an audit

## Exact Next Action

1. Re-fetch PR #103 final head after this handoff update.
2. Inspect the exact diff for accidental journal sync/write, state mutation, ledger append/relabel, recovery calls, or startup file scans.
3. Merge only if the **final exact head** passes Change Safety Audit, all provenance/core regressions, repo safety, architecture ownership/config/debt checks, and exact Gunicorn bootstrap smoke.
4. Wait for Railway deployment success and `delegate_ready:true`.
5. Run only `https://trading-bot-clean.up.railway.app/paper/verified-snapshot-journal-ledger-provenance-status`.
6. If root-level verified journal identity/start survives and the valid 55-row ledger is entirely downstream in time, combine that durable runtime evidence with merged PR #45/#46/#48/#52 historical evidence to build a **read-only successor reconstruction** from the exact verified baseline plus immutable post-cutover canonical rows. Compare before any authoritative recovery PR.
7. If journal provenance is also gone, do not guess. Pivot to historical GitHub workflow/handoff artifacts and other durable evidence sources rather than expanding blind state repair.
8. Only after mechanically defended economic recovery: require sane fresh-day reset, one normal forward paper session, and a clean active audit before closing #82 or enabling Stage F/G authority.

## Conversation Continuity Protocol

Stay in the current active project chat through a coherent testing/update sequence. When a move is needed, stop at a clean boundary, refresh this handoff, and start the new chat with:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Treat this conversation as the current active project chat and keep project-status communication here. Verify current main/PR/CI and the canonical Railway clean-service read-only evidence before changing code. Continue from the Exact Next Action. Preserve paper-only authority, hard risk thresholds, canonical ledger history, rules-only execution authority, ML shadow-only execution, and the Issue #82/#84/#94/#96 gates. Do not manually repair account state or clear halts from inference.
```
