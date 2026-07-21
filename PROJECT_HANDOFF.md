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

## Source-Contract Normalization

Current daily serializer version:

`daily-self-check-compactor-2026-07-21-v4-source-contracts`

The serializer now normalizes X-Ray composition, decision audit, blocker audit, starter-valve, and structured Phase 3A sources while retaining a terminal allowlist and route-level replacement.

Commits:

- `cd5cce24c77c840405914f3cc18e8b762ca09c54` — source-contract normalization.
- `b8bb500f0ec67cf7151296e90ab65b62481ac826` — system-wide audit.
- `70185570ee0b106b6f5ca2da084a63af06844942` — handoff update.

## Latest Reliability Hardening — Transactional State and Read-Only Inspection

### State transaction manager

Added:

`state-transaction-manager-2026-07-21-v1`

The runtime now exposes:

`core.update_state(updater, source=..., expected_revision=...)`

This API performs the read, mutation, revision check, backup, and atomic write within one exclusive state transaction. It adds:

- monotonic `_state_revision`;
- `_state_updated_local`;
- `_state_update_source`;
- optional optimistic revision conflict detection;
- no-write behavior when the updater produces no change;
- `/paper/state-transaction-status` as a read-only diagnostic route.

This is an incremental migration mechanism. Existing modules remain compatible with `load_state()` and `save_state()`, while high-risk writers can be moved to `update_state()` individually.

### Entry ownership guard

Updated to:

`entry-pipeline-ownership-guard-2026-07-21-v2-read-only-inspection`

Changes:

1. `status_payload()` now calls `inspect()` and does not repair, patch, or persist state.
2. The ownership status route is read-only.
3. Composition, sanitizer, and X-Ray repair run only when ownership drift is detected or repair is explicitly forced.
4. Healthy ownership checks do not save state.
5. Drift/error telemetry uses `core.update_state()` when available, preventing stale whole-state replacement.
6. Persistence occurs only for installation, drift, repair, or error events.

### Runtime watchdog

Updated `usercustomize.py` to:

`usercustomize-entry-pipeline-composition-2026-07-21-v29-transactional-state`

Changes:

- installs the transaction manager before diagnostic ownership modules;
- adds the transaction status route to governance diagnostics;
- keeps fast startup convergence for the first 30 seconds;
- slows subsequent drift checks from every 0.1 seconds to every 30 seconds;
- healthy ownership checks are no-op/read-only and no longer create repeated state writes;
- terminal daily serialization remains the final route-level reassertion.

### Files changed

- `state_transaction_manager.py`
- `entry_pipeline_ownership_guard.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Commits

- `d8809adb8a2c459d0a24eab70baa27ba879facd5` — transactional state mutation API.
- `9787dedebab9979e8f1b30d86ae3425673fd640f` — read-only ownership inspection and drift-only persistence.
- `9672b33290e3c23285f1f0e81debf3c76f3da3f2` — reduced watchdog pressure and transaction-manager installation.
- Handoff commit: the commit updating this file.

## System-Wide Audit

Full report:

`SYSTEM_WIDE_AUDIT_2026-07-21.md`

### Highest-priority findings

1. **State writes were atomic but not transactional.** The new transaction manager establishes the migration path; existing high-risk writers still need gradual conversion.
2. **The startup watchdog created write amplification.** Frequency and no-op ownership writes are now reduced.
3. **Some status GET paths have side effects.** Ownership inspection is now read-only; X-Ray and other modules still require staged inspect/install/repair separation.
4. **State authority is split.** Some modules prefer disk while others prefer `core.portfolio`.
5. **Scanner telemetry lacks a common cycle ID.** Decision audit, blocker audit, X-Ray, and post-harvest counts can refer to different cycles.
6. **Broad exception suppression hides failures.** Many patch, registration, and persistence errors remain silently ignored.
7. **Runtime ownership remains monkeypatch-heavy.** A declarative pipeline builder remains the long-term target.
8. **Diagnostic telemetry still writes the trading state in several modules.** These writers should migrate to transactions or separate diagnostic storage.

### Remaining remediation order

1. Migrate X-Ray and other diagnostic writers to `core.update_state()`.
2. Split X-Ray and remaining status modules into read-only `inspect`, explicit `install`, and explicit `repair` APIs.
3. Propagate one cycle ID through scanner, blocker, X-Ray, entries, rotations, and post-harvest.
4. Consolidate disk/in-memory state authority.
5. Move non-critical diagnostic telemetry away from the primary trading-state document.
6. Replace public monkeypatch accumulation with one declarative entry-pipeline builder.
7. Add concurrency and source-contract regression tests.

## Safety / Authority Impact

These changes affect persistence and diagnostics only:

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

The transaction manager is intentionally not added to the compact daily payload yet. Its route is available for deep diagnostics, but routine validation must remain `/paper/self-check` only.

A scanner source mismatch may remain until shared cycle IDs are implemented. It should not by itself change engine health.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error. Do not run mutating repair or execution endpoints during routine validation.
