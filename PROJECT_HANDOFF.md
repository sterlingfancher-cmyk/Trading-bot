# Automated Trading Project Handoff — Updated July 21, 2026

## Standing Rule

Every code/configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Full diagnostics: `https://trading-bot-clean.up.railway.app/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Strict stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## Latest Runtime Evidence — July 21, 2026, 12:53:41 CDT

The v3 terminal route was successfully installed and prevented verbose payload expansion:

- `terminal_compaction_applied: true`
- compact account truth was correct;
- cash: 10111.46;
- equity: 10864.08;
- positions: DELL and QQQ;
- realized total: +733.97;
- unrealized PnL: +130.12;
- execution rows: 83;
- wins/losses: 34/16;
- self-defense inactive;
- intraday drawdown: 0.06%;
- starter valve populated;
- full diagnostics URL populated.

The latest duplicate-reason TypeError remained historical at July 20, 12:01:39 CDT. Active-callsite errors remained at 10 while invocations remained at 85.

The route serializer was structurally complete, but source normalization was incomplete:

- persisted X-Ray state used `composition`, while the serializer expected `composition_status`;
- native decision audit nested scanner fields under `latest_cycle`;
- ML readiness could come from the Phase 3A gate rather than flattened decision-audit fields;
- this produced false null pipeline/ML fields and a false daily warning.

## Latest Code Update — Source-Contract Normalization

### Version

`daily-self-check-compactor-2026-07-21-v4-source-contracts`

### Fixes

1. Normalizes X-Ray composition from `composition_status`, persisted `composition`, `last_cycle.composition`, or `last_meaningful_cycle.composition`.
2. Supports diagnostic status functions that use either a no-argument contract or a core-runtime argument.
3. Normalizes native decision audit fields from `latest_cycle`, `post_harvest`, `risk_book`, and `ml_shadow`.
4. Reads structured Phase 3A readiness from `ml_phase3a_early_paper_gate` rather than depending on recommendation text.
5. Preserves decision-audit and blocker-audit signal counts as separate source-labelled values.
6. Keeps the terminal allowlist and route-level replacement.
7. Adds `source_contracts_normalized: true`.
8. Keeps reporting-only authority: no trading, threshold, sizing, candidate, order, risk-control, live-authority, or ML-authority changes.

### Files changed

- `daily_self_check_compactor.py`
- `SYSTEM_WIDE_AUDIT_2026-07-21.md`
- `PROJECT_HANDOFF.md`

### Commits

- `cd5cce24c77c840405914f3cc18e8b762ca09c54`
  - Normalized X-Ray, decision-audit, blocker-audit, starter-valve, and ML source contracts.
  - Eliminated false compact warnings caused by schema differences.
- `b8bb500f0ec67cf7151296e90ab65b62481ac826`
  - Added the system-wide architecture and reliability audit.
- Handoff commit: the commit updating this file.

## System-Wide Audit

Full report:

`SYSTEM_WIDE_AUDIT_2026-07-21.md`

### Highest-priority findings

1. **State writes are atomic but not transactional.** Independent modules can load the same revision and later overwrite each other's subtree updates with stale whole-state saves.
2. **The startup watchdog creates write amplification.** It runs every 0.1 seconds for 1,200 iterations and repeatedly invokes ownership/status modules; the ownership guard saves state even when no drift exists.
3. **Some status GET paths have side effects.** Status builders can patch or enforce runtime wrappers and can write telemetry, so observation can alter the system being observed.
4. **State authority is split.** Some modules prefer disk, while others prefer `core.portfolio`, producing valid but different snapshots.
5. **Scanner telemetry lacks a common cycle ID.** Decision audit, blocker audit, X-Ray, and post-harvest counts can refer to different cycles.
6. **Broad exception suppression hides failures.** Many patch, registration, and persistence errors are silently ignored.
7. **Runtime ownership remains monkeypatch-heavy.** A single declarative pipeline builder would be safer than repeated public-callable replacement.
8. **Diagnostic telemetry writes the whole trading state.** Non-critical diagnostics can participate in stale-state overwrite risk.

### Audit remediation order

1. Add transactional state mutation with a monotonic state revision.
2. Make stable ownership checks read-only and slow the watchdog.
3. Separate `inspect`, `install`, and `repair` APIs.
4. Propagate one cycle ID through scanner, blocker, X-Ray, entries, rotations, and post-harvest.
5. Move diagnostic telemetry away from whole-state writes.
6. Consolidate disk/in-memory state authority and ML readiness authority.
7. Replace public monkeypatch accumulation with one declarative entry-pipeline builder.
8. Add source-contract and concurrency tests.

## Safety / Authority Impact

The v4 repair and audit documentation are reporting/governance changes only:

- no internal risk check removed;
- no threshold changes;
- no sizing changes;
- no scanner/candidate changes;
- no order-placement changes;
- no live authority added;
- no ML execution authority added;
- no cooldown, self-defense, risk-halt, drawdown, regime, trend, volume, relative-edge, extension, quality, or futures-bias bypass.

## Current Intended Entry Stack

1. `entry_pipeline_xray` outer diagnostic wrapper
2. composition-owned paper-exposure overlay
3. direct closure over `core_entry_pipeline._core_try_entries_and_rotations`
4. clean base participation valve
5. extended-leader starter overlay
6. risk-on starter overlay
7. reason-safe blocker detail wrappers
8. entry-pipeline ownership guard
9. terminal daily route serializer

## Validation Procedure

After Railway redeploys, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- `version: daily-self-check-compactor-2026-07-21-v4-source-contracts`;
- `terminal_compaction_applied: true`;
- `source_contracts_normalized: true`;
- no verbose structures outside the compact allowlist;
- populated account, risk, pipeline, starter, and ML fields;
- stable entry stack;
- no newly timestamped recursion or duplicate-reason error.

A scanner source mismatch may remain until shared cycle IDs are implemented. It should not by itself change engine health.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error. Do not run mutating repair or execution endpoints during routine validation.