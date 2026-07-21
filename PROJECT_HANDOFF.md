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

## Latest Validated Runtime Evidence — July 21, 2026, 19:07:46

The compact self-check passed with no warnings:

- `overall: pass`
- `status: ok`
- `health.warnings: []`
- `terminal_compaction_applied: true`
- `source_contracts_normalized: true`
- `cycle_aware_scanner_comparison: true`
- `runtime_reliability_overlay_version: runtime-reliability-overlay-2026-07-21-v2-entry-contract`

Account and performance snapshot:

- cash: 10111.46
- equity: 10864.08
- positions: DELL and QQQ
- execution rows: 83
- realized total: +733.97
- unrealized PnL: +131.58
- wins/losses: 34/16

Risk snapshot:

- self-defense inactive
- daily loss: 0.0%
- intraday drawdown: 0.047%
- feedback loop clear

Entry-pipeline structure:

- `stack_stable: true`
- `recursion_safe: true`
- `direct_core_base: true`
- `participation_valve_chain_cycle_free: true`
- current callable: `entry_pipeline_xray.wrapped`
- inner callable: `entry_pipeline_composition_guard.composed`

The duplicate-reason TypeError remains historical at July 20, 12:01:39 CDT. Active-callsite invocations/errors remain 85/10, so no new occurrence is present.

Scanner reporting is now correctly non-assertive without shared cycle identity:

- decision count: 54
- blocker-audit count: 42
- count difference: 12
- `same_cycle_comparison: false`
- `source_mismatch: null`
- `snapshot_alignment: unverified_without_shared_cycle_id`

This is informational only and no longer creates a false health warning.

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

## Runtime Reliability Overlay

Version:

`runtime-reliability-overlay-2026-07-21-v2-entry-contract`

The overlay performs four authority-neutral functions:

1. Entry Pipeline X-Ray persistence uses `core.update_state()` when available.
2. X-Ray status inspection is read-only.
3. Scanner count comparison is cycle-aware and does not label unaligned snapshots as a confirmed mismatch.
4. Compact entry-pipeline structural fields are normalized from the dedicated read-only composition inspector.

The compatibility layer restores, when absent from X-Ray telemetry:

- `entry_pipeline.stack_stable`;
- `entry_pipeline.participation_valve_chain_cycle_free`;
- `entry_pipeline.recursion_safe`;
- `entry_pipeline.direct_core_base`.

It removes only a resolved compact-source warning and promotes `overall` back to `pass` only when no warnings or failed required paths remain. Genuine runtime, route, risk, or source failures remain visible.

## System-Wide Audit Progress

Full report:

`SYSTEM_WIDE_AUDIT_2026-07-21.md`

Completed:

1. Added transactional state mutation with monotonic revision support.
2. Made entry ownership inspection read-only.
3. Removed healthy ownership no-op writes.
4. Reduced watchdog pressure after startup convergence.
5. Migrated X-Ray telemetry persistence to transactional updates.
6. Made X-Ray status inspection read-only.
7. Prevented unaligned scanner snapshots from producing a false health warning.
8. Restored compact structural fields from their dedicated read-only authority.
9. Revalidated the compact runtime as pass/ok with zero warnings.

## Next-Phase Recommendations

Infrastructure is stable enough to pause broad reliability patching. Future infrastructure changes should be narrowly scoped, regression-tested, and justified by a concrete failure or measurable operational benefit.

### Priority 1 — Shared cycle identity

Propagate one immutable `cycle_id` from the cycle coordinator through:

- scanner output;
- decision audit;
- blocked-entry reason audit;
- X-Ray telemetry;
- entries;
- rotations;
- post-harvest diagnostics.

Acceptance criteria:

- every producer reports the same cycle ID for one engine cycle;
- same-cycle count comparisons become deterministic;
- cross-cycle snapshots are explicitly rejected from mismatch calculations;
- no trading, risk, sizing, or execution behavior changes.

### Priority 2 — Improve opportunity quality and participation

Shift engineering attention from diagnostics to measurable paper-trading performance:

- evaluate scanner-universe breadth and data-quality limits;
- increase valid opportunities without weakening risk, extension, quality, volume, relative-edge, futures-bias, cooldown, or self-defense controls;
- measure candidate-to-entry conversion by regime and blocker category;
- separate insufficient opportunity flow from intentional risk blocking.

Any scanner or participation change must be tested against a baseline and must not be justified solely by increasing trade count.

### Priority 3 — Phase 3A ML advisory evaluation

Continue ML in advisory-only paper mode:

- retain rule thresholds and risk controls as authoritative;
- log ML-versus-rules disagreement and subsequent outcomes;
- evaluate incremental precision, recall, expectancy, drawdown, and false-positive cost;
- prevent ML from bypassing any hard risk or eligibility gate.

No greater ML authority should be considered until the evidence benchmark is met and advisory results show repeatable improvement over rules alone.

### Priority 4 — Evidence accumulation before authority changes

Current evidence is 83 execution rows, below the stronger-authority benchmark of 150 execution rows and 100 observed outcomes.

Before considering any live or stronger ML authority:

- reach at least 150 execution rows;
- reach at least 100 observed outcomes;
- validate results across multiple market regimes;
- confirm acceptable drawdown and loss clustering;
- confirm no new runtime, state-integrity, recursion, or duplicate-reason failures;
- retain paper-only operation until a separate explicit approval decision.

### Deferred architectural work

The following remain valid but should not displace performance work unless they become operationally necessary:

1. Migrate additional high-risk diagnostic writers to `core.update_state()`.
2. Consolidate disk and `core.portfolio` snapshot authority.
3. Move non-critical diagnostics out of the primary trading-state document.
4. Replace accumulated runtime monkeypatching with one declarative pipeline builder.
5. Add concurrency and source-contract regression tests.

## Safety / Authority Policy

Current and recommended work must preserve:

- all internal risk checks;
- existing sizing limits;
- cooldowns;
- self-defense and drawdown halts;
- regime, trend, volume, relative-edge, extension, quality, and futures-bias gates;
- paper-only broker authority;
- no ML execution authority;
- no automatic promotion to live trading.

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

For routine validation, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- `overall: pass`;
- `status: ok`;
- `health.warnings: []`;
- `version: daily-self-check-compactor-2026-07-21-v4-source-contracts`;
- `terminal_compaction_applied: true`;
- `source_contracts_normalized: true`;
- `cycle_aware_scanner_comparison: true`;
- `runtime_reliability_overlay_version: runtime-reliability-overlay-2026-07-21-v2-entry-contract`;
- `entry_pipeline.stack_stable: true`;
- `entry_pipeline.recursion_safe: true`;
- `entry_pipeline.direct_core_base: true`;
- `entry_pipeline.participation_valve_chain_cycle_free: true`;
- no newly timestamped recursion or duplicate-reason error.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error. Do not run mutating repair or execution endpoints during routine validation.

## Latest Documentation Commit

This handoff update records the validated pass state and establishes the prioritized next-phase roadmap. No runtime trading code, risk controls, thresholds, sizing, scanner behavior, execution behavior, live authority, or ML authority changed in this documentation-only update.
