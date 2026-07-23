# Automated Trading Project Handoff — Updated July 23, 2026

## Standing Rule

Every code or configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Autonomous Engineering Workflow

Continue sequential diagnostic, observability, reliability, documentation, and advisory-only milestones without waiting for approval after each successful validation. Pause for approval before changing executable-universe membership, scanner or signal results, entry/exit logic, thresholds, risk controls, position sizing, order placement, ML decision authority, live-trading authority, or a material architecture decision with multiple reasonable behavioral outcomes.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `/paper/self-check`
- Full diagnostics: `/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## July 23 Morning Baseline

The July 23 compact self-check generated at `2026-07-23 15:28:59` passed with:

- `overall: pass`
- `status: ok`
- service running with no required-path failures or warnings
- cash/equity: `10970.12`
- realized today: `112.74`
- realized total: `970.14`
- execution rows: `88`
- wins/losses: `36 / 18`
- open positions: `0`
- entry pipeline stable, recursion-safe, and direct-core based
- no newly timestamped entry-pipeline error
- ML remains advisory-only with no live authority

Scanner reporting showed:

- decision signals: `54`
- blocker-audit signals: `54`
- count difference: `0`
- reason coverage: `97.44%`
- missing reason rows: `1`

The remaining observability defect was explicit:

- `decision_cycle_id: null`
- `blocker_cycle_id: null`
- `same_cycle_comparison: false`
- `snapshot_alignment: unverified_without_shared_cycle_id`

The test also contained stale-looking cross-cycle telemetry: the starter valve's last reason referenced too many positions while the current account had zero positions, and historical blocker rows referenced self-defense while the current risk snapshot reported the feedback loop clear. These are treated as freshness/cycle-alignment issues, not evidence for changing trading rules.

## Runtime Reliability v3 — Market Data Guard

Version: `market-data-resilience-2026-07-22-v1`

Route: `/paper/provider-health-status`

Behavior:

- bounds the core yfinance request timeout at 8 seconds by default;
- records per-symbol timing and outcomes;
- tracks successes, failures, timeouts, empty responses, and circuit skips;
- opens a short circuit after repeated provider failures;
- preserves the legacy unavailable-data contract by returning `None` on failed/empty downloads;
- does not alter signals, thresholds, sizing, risk, order logic, executable universe, ML authority, or live authority.

The July 23 routine self-check passed after deployment. Direct provider-health validation remains required because the compact self-check does not expose provider counters.

## Shared Cycle Identity

Base version: `shared-cycle-identity-2026-07-22-v1`

Route: `/paper/shared-cycle-identity-status`

The base module creates one immutable cycle ID at scanner invocation and stamps transactional state updates. The morning evidence showed that two diagnostic producers bypass that transactional path:

- `decision_audit_consolidation.build_payload` writes directly to in-memory diagnostic state;
- `blocked_entry_reason_audit.build_payload` is a derived read-only producer.

Therefore the scanner-generated ID existed at runtime but was not reaching the compact decision/blocker comparison.

## Cycle Alignment Overlay — July 23

Version: `cycle-alignment-overlay-2026-07-23-v1`

Route: `/paper/cycle-alignment-status`

The overlay:

- stamps the decision-audit payload and its latest-cycle section with the scanner runtime cycle ID;
- stamps the derived blocker-audit payload with the matching decision/scanner runtime cycle ID;
- repairs the outer daily compactor after the runtime reliability wrapper has executed;
- reports non-null decision and blocker cycle IDs when a scanner cycle exists;
- compares counts only when the producer IDs match;
- reports the metadata source for each ID (`producer`, runtime fallback, or unavailable);
- augments the shared-cycle status route with producer-level cycle IDs;
- preserves the runtime reliability wrapper marker to prevent watchdog wrapper accumulation.

This is metadata/reporting behavior only. It does not change scanner arguments or results, candidate selection, thresholds, entries, exits, risk controls, sizing, orders, ML authority, or live authority.

## Current Scanner v2 Modules

1. `scanner-v2-shadow-universe-2026-07-21-v2-leadership-clusters`
2. `missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`
3. `scanner-v2-shadow-quality-trace-2026-07-21-v1`
4. `scanner-v2-shadow-composite-score-2026-07-21-v1`
5. `scanner-v2-theme-confidence-overlay-2026-07-21-v1`
6. `scanner-v2-candidate-lifecycle-trace-2026-07-21-v1`
7. `shared-cycle-identity-2026-07-22-v1`
8. `cycle-alignment-overlay-2026-07-23-v1`

Executable-universe expansion remains deferred until repeated paper evidence supports a separately reviewed promotion gate.

## Safety and Authority Boundary

Current work preserves:

- no live authority;
- no ML execution authority;
- no order placement;
- no threshold changes;
- no sizing or risk-control changes;
- no executable-universe mutation;
- no scanner-result modification;
- all existing cooldown, self-defense, drawdown, regime, trend, volume, relative-edge, extension, quality, and futures-bias controls.

## Files and Commits

- `market_data_resilience.py`
  - `b3f9d86bdceb23b43bcaf3817bc5634582abfb4b`
- `cycle_alignment_overlay.py`
  - `a95fab9d449723e13270ec3b4d53d2b164fb8360`
- `usercustomize.py`
  - Runtime Reliability registration: `3e034bdc1100653472a80d5fc255195601082515`
  - Cycle alignment registration: `2e85f1dbe3c14f372b9fe4c4cf5a375bad2be9b2`
- `PROJECT_HANDOFF.md`
  - this branch commit documents the July 23 baseline and cycle-alignment repair.

## Validation After Merge and Railway Redeploy

Run in this order:

1. `https://trading-bot-clean.up.railway.app/paper/self-check`
2. `https://trading-bot-clean.up.railway.app/paper/cycle-alignment-status`
3. `https://trading-bot-clean.up.railway.app/paper/shared-cycle-identity-status`
4. `https://trading-bot-clean.up.railway.app/paper/provider-health-status`

Expected cycle-alignment fields after at least one normal scanner cycle:

- `cycle_alignment_overlay_version: cycle-alignment-overlay-2026-07-23-v1`
- non-null `scanner.decision_cycle_id`
- non-null `scanner.blocker_cycle_id`
- `scanner.same_cycle_comparison: true`
- `scanner.snapshot_alignment: same_cycle`
- `scanner.count_difference: 0` when both producers still report 54 signals
- `scanner.source_mismatch: false` when counts match
- installation flags true on `/paper/cycle-alignment-status`
- producer IDs visible on `/paper/shared-cycle-identity-status`

Expected provider-health fields:

- `status: ok`
- `overall: pass`
- `installed: true`
- `request_timeout_seconds: 8.0` unless overridden
- authority fields false
- bounded recent events and no single-symbol 30-second worker stall

Use `/paper/full-self-check` only for a failed routine check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Next Steps

Proceed autonomously in this order:

1. Merge the cycle-alignment branch after diff review.
2. Validate the four routes above after Railway redeploy.
3. Confirm producer-level cycle IDs remain aligned across at least two normal cycles.
4. Replace the remaining single `reason_detail_missing` row with its explicit underlying blocker source.
5. Add freshness metadata to last-known starter-valve and blocker summaries so historical telemetry cannot be mistaken for current account state.
6. Continue candidate lifecycle and opportunity-attribution evidence collection.
7. Keep strategy, thresholds, sizing, risk, ML authority, and live authority unchanged until evidence supports a separately reviewed proposal.

No filter should be relaxed solely because a stock finished strongly.
