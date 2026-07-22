# Automated Trading Project Handoff — Updated July 22, 2026

## Standing Rule

Every code or configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Autonomous Engineering Workflow

Continue sequential diagnostic, observability, reliability, documentation, and advisory-only milestones without waiting for approval after each successful validation. Select the next engineering task from current evidence, update this handoff, and validate the deployment after each milestone.

Pause for user approval before any change that would alter:

- executable-universe membership;
- scanner or signal results;
- entry or exit logic;
- thresholds;
- risk controls or position sizing;
- order placement;
- ML decision authority;
- live-trading authority;
- or a material architecture decision with multiple reasonable behavioral outcomes.

Provide the user a completion update after each implemented milestone with commits, validation route, safety impact, and next action.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `/paper/self-check`
- Full diagnostics: `/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## Latest Runtime Baseline

The July 22 mid-day compact self-check passed with `overall: pass`, `status: ok`, no warnings, stable recursion-safe direct-core entry pipeline, paper equity of 10893.98, 85 execution rows, 35 wins, 17 losses, and no newly timestamped runtime error. The historical duplicate-reason TypeError remains dated July 20 and is not new.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error.

## Scanner v2 Evidence

The July 21 missed-opportunity sample included BE, NVTS, STX, NUAI, CRWV, and ONDS.

Validated findings:

- all six exceeded the 8% daily-move threshold;
- all six passed minimum price, average-volume, and average-dollar-volume floors;
- BE, NVTS, NUAI, CRWV, and ONDS were executable-universe coverage misses;
- STX was in the executable universe but had no persisted scanner, decision, blocker, or audit observation;
- the primary issue is discovery and observation, not basic tradability.

## Current Scanner v2 Modules

1. `scanner-v2-shadow-universe-2026-07-21-v2-leadership-clusters`
   - Route: `/paper/scanner-v2-shadow-universe-status`
2. `missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes`
   - Route: `/paper/missed-opportunity-post-close-audit-status`
3. `scanner-v2-shadow-quality-trace-2026-07-21-v1`
   - Route: `/paper/scanner-v2-shadow-quality-trace-status`
4. `scanner-v2-shadow-composite-score-2026-07-21-v1`
   - Route: `/paper/scanner-v2-shadow-composite-score-status`
5. `scanner-v2-theme-confidence-overlay-2026-07-21-v1`
   - Route: `/paper/scanner-v2-theme-confidence-status`
   - Requires at least two scored members before treating a theme as confirmed leadership.
6. `scanner-v2-candidate-lifecycle-trace-2026-07-21-v1`
   - Route: `/paper/scanner-v2-candidate-lifecycle-trace-status`
   - Pass-through scan instrumentation; does not alter scanner arguments or results.
7. `shared-cycle-identity-2026-07-22-v1`
   - Route: `/paper/shared-cycle-identity-status`
   - Creates one immutable cycle ID at scanner invocation.
   - Propagates cycle metadata through transactional scanner, decision, blocker, X-Ray, journal, rotation, and post-harvest state updates.
   - Stamps only records changed during the associated cycle.
   - Does not alter scanner inputs/results, candidates, thresholds, risk, sizing, orders, ML authority, or live authority.

## Shared Cycle Identity Milestone

The July 22 update addresses the compact self-check fields:

- `decision_cycle_id: null`
- `blocker_cycle_id: null`
- `same_cycle_comparison: false`
- `snapshot_alignment: unverified_without_shared_cycle_id`

Expected behavior after Railway redeploy and at least one normal scanner/entry cycle:

- scanner-generated cycle ID is available in `/paper/shared-cycle-identity-status`;
- decision and blocker audit records receive the same immutable `cycle_id` when written during that cycle;
- `/paper/self-check` can move toward `same_cycle_comparison: true` and verified same-cycle alignment;
- count mismatches are evaluated only when producer records belong to the same cycle.

This is an observability metadata change only.

## Safety and Authority Boundary

Current work preserves:

- no live authority;
- no ML execution authority;
- no order placement;
- no threshold changes;
- no sizing or risk-control changes;
- no executable-universe mutation;
- no scanner-result modification;
- existing cooldown, self-defense, drawdown, regime, trend, volume, relative-edge, extension, quality, and futures-bias controls.

Executable-universe expansion remains deferred until repeated evidence supports a separately reviewed paper-only promotion gate.

## Files and Commits

- `scanner_v2_shadow_universe.py`
  - `227ac0d4d559e0aff1140456b48bbc54ad6fd36b`
  - `50d84797c093aa6aeb90c1b0fd9b5da5027eb7aa`
- `missed_opportunity_post_close_audit.py`
  - `fbdfab96d46a834efa0844da8a428032640a283d`
  - `e8295b01a1e21b7e20850196a812c4925488ab1f`
- `scanner_v2_shadow_quality_trace.py`
  - `c4321dba229a0b3d12020e4464597f810014ae5a`
- `scanner_v2_shadow_composite_score.py`
  - `00214d50538fbc065402c02e6c75cc4d7856debd`
- `scanner_v2_candidate_lifecycle_trace.py`
  - `fd2a2df4d0a11e6dd48332b5ff7038c3f309bb13`
- `scanner_v2_theme_confidence_overlay.py`
  - `31b96cf50e0876bc97ce002610a795c1eb2a2f59`
- `shared_cycle_identity.py`
  - `964d32c3370468c4532e11ce87e11ffae32f0c3c`
- `usercustomize.py`
  - `147101f2c34a3be6b33611549271fc8d5d730757`
  - `54c49869cd90ce6812821ad3cb75bdf7249fe9d8`
- `PROJECT_HANDOFF.md`
  - this commit documents autonomous workflow and the shared-cycle milestone.

## Validation

After Railway redeploys, run:

1. `https://trading-bot-clean.up.railway.app/paper/self-check`
2. `https://trading-bot-clean.up.railway.app/paper/shared-cycle-identity-status`
3. After at least one normal scanner/entry cycle, run both links again.

Expected shared-cycle route fields:

- `status: ok`
- `overall: pass`
- `version: shared-cycle-identity-2026-07-22-v1`
- `scan_signals_patched_for_identity_only: true` in installation status or runtime registration
- all authority fields false
- a non-null `last_cycle_id` after a scanner cycle
- increasing `records_with_cycle_id` as decision and blocker records are written
- `same_cycle_alignment: true` once at least two relevant records share the same ID

## Next Steps

Proceed autonomously in this order:

1. Validate routine self-check after redeploy.
2. Validate shared-cycle route before and after a normal cycle.
3. Confirm decision and blocker records receive the same cycle ID.
4. If alignment remains incomplete, identify which producer bypasses transactional state updates and add metadata-only instrumentation at that producer.
5. Replace remaining `reason_detail_missing` rows with explicit underlying blocker attribution.
6. Expand candidate lifecycle persistence and repeated candidate-to-entry/outcome evidence.
7. Keep strategy, thresholds, sizing, risk, ML authority, and live authority unchanged until evidence supports a separately reviewed proposal.

No filter should be relaxed solely because a stock finished strongly.
