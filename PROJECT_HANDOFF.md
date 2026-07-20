# Automated Trading Project Handoff — Updated July 20, 2026

## Standing Rule

Every code/configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine test: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Strict stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## Latest Runtime Evidence — July 20, 2026, 15:21:01 CDT

The duplicate-reason TypeError repair succeeded:

- No new `_patched_participation_valve_ok.<locals>.blocked() got multiple values for argument 'reason'` timestamps appeared after 12:01:39 CDT.
- X-Ray active-callsite error count remained 10 while invocation count advanced from 41 to 44.
- The deterministic participation helper chain remained cycle-free.

A separate runtime composition drift was then observed:

- Persisted composition at 15:21:02 CDT showed the correct v4 stack.
- Live status at 15:21:07 CDT showed `paper_exposure_rotation.patched_try_entries_and_rotations` as the public callable.
- `stack_stable: false`
- `direct_core_base: false`
- `recursion_safe: false` in the live callable status
- The helper chain itself still reported `participation_valve_chain_cycle_free: true`.

This proved that the legacy `paper_exposure_rotation._patch_try_entries` path could run after composition/X-Ray and replace `app.try_entries_and_rotations`.

Risk behavior remained appropriate:

- Market mode: `crash_warning`
- Regime: bear
- Risk score: 17
- Self-defense active after a realized daily loss near 1.14%
- Open positions: DELL and QQQ
- Equity: 10829.14
- Cash: 10111.46
- Realized today: -123.71
- Total realized: +733.97
- Unrealized: +95.18

No risk control should be loosened because of this composition repair.

## Latest Code Update — Entry Pipeline Ownership Guard

### Root cause

`paper_exposure_rotation.apply_runtime_overrides()` always called its legacy `_patch_try_entries()` function. When the current public callable was X-Ray rather than the inner composed function, the legacy marker check did not recognize the stack as already managed. It then wrapped and replaced the public callable, displacing both X-Ray and the composition-owned direct-core metadata.

### Fix

Added `entry_pipeline_ownership_guard.py` as the final runtime authority for `app.try_entries_and_rotations`.

It performs four functions:

1. Replaces `paper_exposure_rotation._patch_try_entries` with an ownership-managed no-op. Paper exposure retains its bucket, aggression, sector-limit, and rotation helper patches, but it may no longer replace the public entry callable.
2. Calls `entry_pipeline_composition_guard.enforce()` to restore the deterministic inner stack.
3. Reapplies the starter-valve reason sanitizer and Entry Pipeline X-Ray so X-Ray remains outermost.
4. Persists drift telemetry including counters, detection and repair timestamps, and metadata for the displaced callable.

Ownership token:

`composition-guard-inner+xray-outer`

Expected owned stack:

1. `entry_pipeline_xray` outer diagnostic wrapper
2. composition-owned paper-exposure overlay
3. direct closure over `core_entry_pipeline._core_try_entries_and_rotations`
4. clean base participation valve
5. extended-leader starter overlay
6. risk-on starter overlay
7. reason-safe blocker detail wrappers

`usercustomize.py` now loads the ownership guard after X-Ray and reasserts it again after all other runtime modules during every watchdog pass.

### Files changed

- `entry_pipeline_ownership_guard.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Versions

- `entry-pipeline-ownership-guard-2026-07-20-v1`
- `usercustomize-entry-pipeline-composition-2026-07-20-v26-ownership-guard`
- Existing composition: `entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- Existing participation chain: `participation-valve-chain-2026-07-17-v1`
- Existing sanitizer: `starter-valve-reason-sanitizer-2026-07-20-v1`

### Commits

- `f3ecc3db1eebc0a645fd7806e54112ca4f660969`
  - Added ownership enforcement, legacy public-wrapper suppression, drift detection, drift repair, and status route.
- `49614d128f337f69b49b9e0224383ca6a171b8eb`
  - Added ownership guard to startup and watchdog ordering.
  - Reasserts ownership after all other runtime modules execute.
  - Added ownership status to optional self-check governance endpoints.
- Handoff commit: the commit that updates this file in the same work session.

### Routes

- Routine: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Ownership: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-ownership-status`
- Composition: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-composition-status`
- X-Ray: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-xray-status`
- Sanitizer: `https://trading-bot-clean.up.railway.app/paper/starter-valve-reason-sanitizer-status`

## Expected Runtime Evidence After Redeploy

Routine self-check should show the public callable as X-Ray, not `paper_exposure_rotation.patched_try_entries_and_rotations`.

Ownership telemetry should report:

- Version: `entry-pipeline-ownership-guard-2026-07-20-v1`
- `owner_token: composition-guard-inner+xray-outer`
- `legacy_public_patch_disabled: true`
- `owned: true`
- `current_callable.xray_version` populated
- `inner_callable.composition_version: entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- `inner_callable.direct_core_base: true`
- `drift_detected_total` and `drift_repaired_total` available in counters

Composition/X-Ray should report:

- `stack_stable: true`
- `direct_core_base: true`
- `recursion_safe: true`
- `participation_valve_chain_cycle_free: true`
- X-Ray current callable outermost
- no new duplicate-reason TypeError timestamps
- no new recursion timestamps

Historical X-Ray errors may remain in state. Validation must compare timestamps and counters after redeploy.

## Safety / Authority Impact

- Runtime composition and diagnostics repair only
- No threshold changes
- No sizing changes
- No candidate-list changes
- No order-placement changes
- No live authority added
- No ML authority added
- No cooldown bypass
- No self-defense bypass
- No risk-halt bypass
- No drawdown-control bypass
- No trend, volume, relative-edge, futures-bias, or market-regime bypass
- Paper exposure helper policies remain active; only its independent public-callable wrapper is disabled

## Prior Key Repairs

- `fc002ce9a7daabcbcb951d298b7d0cc17c7da3ac` — duplicate-reason sanitizer
- `ac423cb488aaf0753340c88caab3f8114d80193e` — deterministic, cycle-free participation chain
- `daac00d02a969cde5fcbaa8c033a7be034bbc78a` — direct-core composition repair
- `9ba549feaa3eb0e28e23bd013157d7a391cc0376` — X-Ray v3 with error and meaningful-cycle telemetry
- `06f7189179076f656642371250d613a90807c2e6` — prior startup/watchdog ordering

## State and Reporting Notes

- X-Ray preserves both latest and latest meaningful cycles.
- Historical recursion and TypeError records remain visible until replaced; use timestamps to distinguish pre-fix and post-fix errors.
- The persistent TEM post-harvest row still reports `reason_not_available_in_state_snapshot`; this remains diagnostic debt rather than a risk/authority issue.
- Execution rows and observed outcomes have previously moved backward in state. Continue monitoring for stale-state writes or reconciliation changes.
- Do not run repair routes unless a specific malformed-state condition is confirmed.

## Validation Procedure

After Railway redeploys, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm service health, ownership guard presence, X-Ray outermost, stable direct-core composition, cycle-free participation chain, coherent positions/PnL/risk state, and no newly timestamped recursion or duplicate-reason errors.

Do not run mutating repair or execution endpoints as part of routine validation.
