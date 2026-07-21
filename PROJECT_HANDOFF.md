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

## Latest Runtime Evidence — July 21, 2026, 18:38:48

The cycle-aware scanner patch deployed successfully:

- `cycle_aware_scanner_comparison: true`
- `source_mismatch: null`
- `same_cycle_comparison: false`
- `snapshot_alignment: unverified_without_shared_cycle_id`
- raw decision/blocker counts remained visible at 54/42
- runtime overlay v1 was active

Account, risk, ML, current callable, inner callable, recursion safety, and direct-core status remained healthy. The historical duplicate-reason TypeError remained timestamped July 20, 12:01:39 CDT with no new occurrence.

One compact-source regression appeared after X-Ray status became read-only:

- `entry_pipeline.stack_stable` became null;
- `entry_pipeline.participation_valve_chain_cycle_free` became null;
- the compact response downgraded to warn with `compact_source_fields_missing`.

The runtime call chain itself remained intact. The regression was isolated to serializer source normalization because the dedicated composition guard still owns and can inspect those structural fields.

## Current Daily Serializer

Version:

`daily-self-check-compactor-2026-07-21-v4-source-contracts`

It provides terminal allowlisted reporting, normalized source contracts, account/risk truth, structured pipeline status, starter-valve status, and Phase 3A advisory status.

## Transactional State Foundation

Version:

`state-transaction-manager-2026-07-21-v1`

The runtime exposes:

`core.update_state(updater, source=..., expected_revision=...)`

The transaction manager performs locked read-modify-write updates with:

- monotonic `_state_revision`;
- optimistic conflict detection;
- backup plus atomic replacement;
- no-write behavior for unchanged state;
- update-source and timestamp metadata;
- read-only `/paper/state-transaction-status`.

## Entry Ownership Reliability

Version:

`entry-pipeline-ownership-guard-2026-07-21-v2-read-only-inspection`

Ownership status is read-only. Repair and persistence happen only on installation, actual drift, explicit repair, or error. Healthy checks no longer write the complete state.

## Latest Update — Compact Entry Contract Compatibility

### Runtime reliability overlay

Updated to:

`runtime-reliability-overlay-2026-07-21-v2-entry-contract`

The overlay now performs four authority-neutral functions:

1. Entry Pipeline X-Ray persistence uses `core.update_state()` when available.
2. X-Ray status inspection remains read-only.
3. Scanner count comparison remains cycle-aware and does not label unaligned snapshots as a confirmed mismatch.
4. Missing compact entry-pipeline structural fields are normalized from the dedicated read-only `entry_pipeline_composition_guard.status_payload()` source.

The compatibility layer restores, when absent from X-Ray telemetry:

- `entry_pipeline.stack_stable`;
- `entry_pipeline.participation_valve_chain_cycle_free`;
- `entry_pipeline.recursion_safe`;
- `entry_pipeline.direct_core_base`.

It removes only the resolved `entry_pipeline.stack_stable` item from `compact_source_fields_missing`. It promotes `overall: warn` back to `pass` only when no warnings or failed required paths remain. It does not mask genuine runtime, route, risk, or source failures.

### Files changed

- `runtime_reliability_overlay.py`
- `PROJECT_HANDOFF.md`

### Commits

- `4ccc6c22bbe3425f017f6f6f1c411499079d57c0` — transactional X-Ray persistence, read-only X-Ray status, and cycle-aware scanner reporting.
- `bf6450c11ed612f3e1364e20f5b61bf51b946a46` — load the reliability overlay after the terminal serializer.
- `280bc3e485300f35188be54173cf4d6a964ed1f2` — normalize compact entry stability fields from the read-only composition inspector.
- Handoff commit: the commit updating this file.

## System-Wide Audit

Full report:

`SYSTEM_WIDE_AUDIT_2026-07-21.md`

### Remediation progress

Completed:

1. Added transactional state mutation with monotonic revision support.
2. Made entry ownership inspection read-only.
3. Removed healthy ownership no-op writes.
4. Reduced watchdog pressure after startup convergence.
5. Migrated X-Ray telemetry persistence to transactional updates.
6. Made X-Ray status inspection read-only.
7. Prevented unaligned scanner snapshots from producing a false health warning.
8. Restored compact structural fields from their dedicated read-only authority.

Remaining:

1. Propagate one shared cycle ID through scanner, blocker audit, X-Ray, entries, rotations, and post-harvest at the producers.
2. Migrate additional diagnostic writers to `core.update_state()`.
3. Consolidate disk and `core.portfolio` snapshot authority.
4. Move non-critical diagnostics out of the primary trading-state document.
5. Replace accumulated runtime monkeypatching with one declarative pipeline builder.
6. Add concurrency and source-contract regression tests.

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
10. runtime reliability reporting overlay

## Validation Procedure

After Railway redeploys, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- `version: daily-self-check-compactor-2026-07-21-v4-source-contracts`;
- `terminal_compaction_applied: true`;
- `source_contracts_normalized: true`;
- `cycle_aware_scanner_comparison: true`;
- `runtime_reliability_overlay_version: runtime-reliability-overlay-2026-07-21-v2-entry-contract`;
- `entry_pipeline.stack_stable: true`;
- `entry_pipeline.participation_valve_chain_cycle_free: true`;
- `overall: pass` and `status: ok` when no other warning is present;
- no newly timestamped recursion or duplicate-reason error;
- scanner count difference remains visible but does not create a mismatch warning unless the two producers report the same cycle ID.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error. Do not run mutating repair or execution endpoints during routine validation.
