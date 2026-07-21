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

## Latest Runtime Evidence — July 21, 2026, 18:30:59

The compact self-check remained healthy:

- status: `ok`
- overall: `pass`
- cash: 10111.46
- equity: 10864.08
- positions: DELL and QQQ
- execution rows: 83
- realized total: +733.97
- unrealized PnL: +131.58
- wins/losses: 34/16
- self-defense inactive
- intraday drawdown: 0.047%
- entry stack stable, recursion-safe, direct-core-based, and cycle-free
- ML Phase 3A paper advisory gate open
- live ML authority remains none

The duplicate-reason TypeError remained historical at July 20, 12:01:39 CDT. Active-callsite invocations/errors remained 85/10, so no new occurrence was observed.

The only warning was a 54-versus-42 scanner count comparison between decision audit and blocker audit. Those producers did not yet expose a shared cycle ID, so the prior warning could not prove a same-cycle data disagreement.

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

## Latest Update — Transactional X-Ray and Cycle-Aware Scanner Reporting

### Runtime reliability overlay

Added:

`runtime-reliability-overlay-2026-07-21-v1`

The overlay performs three authority-neutral repairs:

1. Entry Pipeline X-Ray persistence now uses `core.update_state()` when available instead of a stale whole-state `load_state()` / `save_state()` sequence.
2. X-Ray `status_payload()` is replaced with a read-only inspector. A GET status request no longer installs, patches, composes, repairs, or persists runtime wrappers.
3. Scanner count comparison is cycle-aware:
   - counts are compared as a true mismatch only when both sources expose the same cycle ID;
   - different or partial cycle IDs are labelled as unaligned snapshots;
   - when neither producer exposes a cycle ID, `source_mismatch` is `null` and `snapshot_alignment` is `unverified_without_shared_cycle_id`;
   - raw decision-audit and blocker-audit counts remain visible, along with `count_difference`;
   - the false `scanner_source_snapshot_mismatch` health warning is removed unless same-cycle evidence exists.

The compact daily payload gains:

- `cycle_aware_scanner_comparison: true`
- `runtime_reliability_overlay_version`
- `scanner.decision_cycle_id`
- `scanner.blocker_cycle_id`
- `scanner.same_cycle_comparison`
- `scanner.count_difference`
- `scanner.snapshot_alignment`

### Runtime loader

Updated `usercustomize.py` to:

`usercustomize-entry-pipeline-composition-2026-07-21-v30-runtime-reliability`

The runtime reliability overlay is loaded after the terminal daily serializer so its read-only X-Ray inspection and cycle-aware scanner normalization remain final. The watchdog reasserts it after the compactor during low-frequency drift checks.

### Files changed

- `runtime_reliability_overlay.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Commits

- `4ccc6c22bbe3425f017f6f6f1c411499079d57c0` — transactional X-Ray persistence, read-only X-Ray status, and cycle-aware scanner reporting.
- `bf6450c11ed612f3e1364e20f5b61bf51b946a46` — load the reliability overlay after the terminal serializer.
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
- `runtime_reliability_overlay_version: runtime-reliability-overlay-2026-07-21-v1`;
- no verbose structures outside the compact allowlist;
- populated account, risk, pipeline, starter, and ML fields;
- stable entry stack;
- no newly timestamped recursion or duplicate-reason error;
- scanner count difference remains visible but does not create a mismatch warning unless the two producers report the same cycle ID.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error. Do not run mutating repair or execution endpoints during routine validation.
