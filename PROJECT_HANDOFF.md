# Automated Trading Project Handoff — Updated July 17, 2026

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

## Latest Runtime Evidence — July 17, 2026, 12:52:31 CDT

The operator supplied a passing infrastructure/self-check payload, but the entry X-Ray proved that the prior recursion repair did not eliminate the actual helper-level cycle:

- `overall: pass`
- No required HTTP failures or warnings
- Cash/equity: 10868.73
- Open positions: 0
- Realized PnL today: +11.08
- Wins today: 2
- Losses today: 3
- Total realized PnL: +868.76
- Execution rows: 87
- Observed outcomes: 54
- Early paper Phase 3A ready: true
- X-Ray active-callsite invocations: 186
- Meaningful cycles: 48
- Active-callsite errors: 47
- Fresh repeated exception through 12:49:01 CDT: `RecursionError: maximum recursion depth exceeded while calling a Python object`
- Last meaningful candidate: NBIS
- Last meaningful path: scanner signal -> active entry call -> prepared candidate -> no final row visible -> recursion error
- Risk-on starter telemetry remained empty because execution failed before the participation result completed

The composition metadata reported `direct_core_base: true`, but the internal participation helper chain was cyclic. The service remained available because X-Ray caught the exception.

## Latest Code Update — Deterministic Participation Valve Chain

### Root cause

The extended-leader starter module and risk-on starter module both patch `core_entry_pipeline._participation_valve_ok` and store the current callable in module-global `_ORIGINAL_FN`.

Repeated startup/watchdog patching could produce this cycle:

1. Extended overlay stores the risk-on overlay as its original.
2. Risk-on overlay stores the extended overlay as its original.
3. A candidate reaches the participation helper.
4. Each overlay calls the other indefinitely.
5. Python raises `RecursionError`.

This explains why the outer entry stack could be structurally correct while meaningful candidate cycles still failed.

### Fix

`entry_pipeline_composition_guard.py` now owns and verifies the participation-helper chain. It installs the chain deterministically:

1. Clean base participation-valve implementation
2. Extended-leader starter overlay
3. Risk-on starter overlay

The clean base implementation is created directly from `core_entry_pipeline` constants and helper functions. It does not reference either overlay.

The guard sets:

- `extended_leader_starter_valve._ORIGINAL_FN = clean_base`
- `risk_on_starter_participation_valve._ORIGINAL_FN = extended_overlay`
- `core_entry_pipeline._participation_valve_ok = risk_on_overlay`

Each layer receives fixed chain metadata. Repeated watchdog calls use a stable fast path when the outer helper already has the correct chain version and role. Neither overlay dynamically recaptures the other.

### Corrected runtime stack

1. `entry_pipeline_xray` outer diagnostic wrapper
2. `paper_exposure_rotation` overlay
3. direct closure over `core_entry_pipeline._core_try_entries_and_rotations`
4. clean base participation valve
5. extended-leader starter overlay
6. risk-on starter overlay

### Files changed

- `entry_pipeline_composition_guard.py`
- `PROJECT_HANDOFF.md`

### New versions

- `entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- `participation-valve-chain-2026-07-17-v1`

### Commits

- `ac423cb488aaf0753340c88caab3f8114d80193e`
  - Added a clean non-overlay participation-valve base.
  - Added deterministic base -> extended -> risk-on composition.
  - Added chain roles and version markers.
  - Added cycle-free status checks.
  - Runs helper-chain repair before the outer-stack stable fast path.
  - Preserved the direct-core entry closure and paper-exposure overlay.
- Handoff commit: the commit that updates this file in the same work session.

### Routes

- Routine: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Composition: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-composition-status`
- X-Ray: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-xray-status`
- Risk-on starter valve: `https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status`
- Core pipeline: `https://trading-bot-clean.up.railway.app/paper/core-entry-pipeline-status`

## Expected Runtime Evidence After Redeploy

Composition route/self-check should show:

- Version: `entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- `stack_stable: true`
- `direct_core_base: true`
- `recursion_safe: true`
- `participation_valve_chain_version: participation-valve-chain-2026-07-17-v1`
- `participation_valve_chain_cycle_free: true`
- participation callable role: `risk_on_outer`
- latest chain status showing:
  - clean base role
  - extended middle role
  - risk-on outer role
  - `cycle_free: true`

X-Ray should remain outermost:

- Version: `entry-pipeline-xray-2026-07-14-v3-composition-errors`
- Patch target: `app.try_entries_and_rotations`
- Wrapped callable pointing to the v4 composed function
- Preserved latest and last-meaningful cycle telemetry

After a fresh open-market candidate cycle:

- no new `RecursionError` timestamps should appear after redeploy
- active-callsite recursion-error counter should stop increasing
- prepared candidates should produce entries, explicit blocker rows, or starter-valve telemetry
- risk-on starter telemetry should begin recording evaluations when quality failures reach the helper

Historical `recent_errors` may remain in state until naturally replaced. Validation must compare timestamps and counters before and after redeploy.

## Safety / Authority Impact

- Composition repair only
- No global threshold changes
- No sizing changes
- No candidate-list changes
- No direct order placement added
- No live authority added
- No ML authority added
- No cooldown bypass
- No self-defense bypass
- No risk-halt bypass
- No drawdown-control bypass
- No trend, volume, or relative-edge bypass
- Existing base, extended-leader, and risk-on starter policies retain their prior thresholds and limits

## Prior Composition and X-Ray Versions

- `entry-pipeline-composition-guard-2026-07-15-v3-recursion-safe`
- `entry-pipeline-composition-guard-2026-07-14-v2-stable-stack`
- `entry-pipeline-xray-2026-07-14-v3-composition-errors`
- `usercustomize-entry-pipeline-composition-2026-07-14-v24-stable-watchdog`
- `one-test-policy-2026-07-14-entry-pipeline-composition-v3`

Prior key commits:

- `daac00d02a969cde5fcbaa8c033a7be034bbc78a` — direct-core outer composition repair
- `627bfeed8b1927a26a281a33ef3a38b446210bf3` — stable composition guard v2
- `9ba549feaa3eb0e28e23bd013157d7a391cc0376` — X-Ray v3 with error details and meaningful-cycle retention
- `06f7189179076f656642371250d613a90807c2e6` — stable startup/watchdog ordering

## State and Reporting Notes

- X-Ray preserves both the latest cycle and latest meaningful cycle.
- Historical recursion errors remain visible until replaced; use timestamps to distinguish pre-fix and post-fix errors.
- The persistent TEM post-harvest row still reports `reason_not_available_in_state_snapshot`; this remains diagnostic debt rather than a risk/authority issue.
- Execution rows and observed outcomes have previously moved backward in state. Continue watching for stale-state writes or reconciliation changes. Do not run repair routes unless a specific malformed-state condition is confirmed.

## Validation Procedure

After Railway redeploys, run:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- `overall: pass`
- `failed_required: []`
- no new warnings
- composition version is `entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- `participation_valve_chain_cycle_free: true`
- `direct_core_base: true`
- `recursion_safe: true`
- X-Ray remains patched and outermost
- positions, PnL, and risk state remain coherent

During the next open-market candidate cycle, verify that no new recursion errors are appended and candidate results become entries, explicit blocker rows, or starter-valve evaluations.

Do not run mutating repair or execution endpoints as part of routine validation.
