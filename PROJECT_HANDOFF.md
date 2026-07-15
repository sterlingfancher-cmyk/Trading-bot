# Automated Trading Project Handoff — Updated July 15, 2026

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

## Latest Runtime Evidence — July 15, 2026, 15:31:10 CDT

The operator supplied a passing infrastructure/self-check payload, but X-Ray showed the composed entry path was functionally failing on meaningful candidate cycles:

- `overall: pass`
- No required HTTP failures or warnings
- Open positions: DELL, QQQ, SNDK
- Equity: 10937.58
- Cash: 9672.49
- Realized PnL today: 0.0
- Unrealized PnL: +79.91
- Daily/intraday drawdown: 1.02%
- Self-defense inactive
- X-Ray active-callsite invocations: 68
- Meaningful cycles: 19
- Active-callsite errors: 19
- Repeated exception: `RecursionError: maximum recursion depth exceeded while calling a Python object`
- Last meaningful candidate: HUT
- Last meaningful path: scanner signal -> active entry call -> prepared candidate -> no final row visible -> recursion error
- Risk-on starter valve still had no candidate evaluations because execution failed before reaching the participation helper

The service remained available because X-Ray caught and recorded the exception. Infrastructure health was good, but meaningful entry execution was broken.

## Latest Code Update — Recursion-Safe Entry Composition

### Root cause

The prior composition guard rebuilt the stack by calling `core_entry_pipeline.apply(core)` and then reading `core.try_entries_and_rotations` back from the public app module. In a runtime containing X-Ray and paper-exposure wrappers, that public callable could already belong to the wrapper chain. The exposure closure could therefore resolve back into the composed/X-Ray path and recurse.

### Fix

`entry_pipeline_composition_guard.py` now captures an immutable direct closure around:

`core_entry_pipeline._core_try_entries_and_rotations(core, ...)`

The paper-exposure overlay calls only that captured closure. It never resolves or calls public `app.try_entries_and_rotations` from inside the composed wrapper.

Corrected stack:

1. `entry_pipeline_xray` outer diagnostic wrapper
2. `paper_exposure_rotation` overlay
3. direct closure over `core_entry_pipeline._core_try_entries_and_rotations`
4. risk-on starter valve on the core participation helper

### File changed

- `entry_pipeline_composition_guard.py`
- `PROJECT_HANDOFF.md`

### New version

- `entry-pipeline-composition-guard-2026-07-15-v3-recursion-safe`

### Commits

- `daac00d02a969cde5fcbaa8c033a7be034bbc78a`
  - Replaced public-callable composition with an immutable direct-core closure.
  - Added `_entry_pipeline_direct_core_base` metadata.
  - Added `direct_core_base` and `recursion_safe` status fields.
  - Stable fast path now requires the direct-core-base marker.
  - Retained paper exposure, X-Ray outer wrapping, and risk-on starter helper patching.
- Handoff commit: recorded by the commit that updates this file in the same work session.

### Routes

- Routine: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Composition: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-composition-status`
- X-Ray: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-xray-status`
- Risk-on starter valve: `https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status`
- Core pipeline: `https://trading-bot-clean.up.railway.app/paper/core-entry-pipeline-status`

## Expected Runtime Evidence After Redeploy

Composition route/self-check should show:

- Version: `entry-pipeline-composition-guard-2026-07-15-v3-recursion-safe`
- `stack_stable: true`
- `direct_core_base: true`
- `recursion_safe: true`
- Inner/composed callable metadata:
  - `core_entry_pipeline_patched: true`
  - populated `core_entry_pipeline_version`
  - `paper_exposure_version: entry-pipeline-composition-guard-2026-07-15-v3-recursion-safe`
  - `direct_core_base: true`

X-Ray should remain outermost and continue showing:

- Version: `entry-pipeline-xray-2026-07-14-v3-composition-errors`
- Patch target: `app.try_entries_and_rotations`
- Wrapped callable pointing to the recursion-safe composed function
- preserved latest and last-meaningful cycle telemetry

After a fresh open-market candidate cycle:

- no new `RecursionError` rows should appear
- active-callsite error counter should stop increasing due to recursion
- prepared candidates should produce either entries, explicit blocked rows, or participation-valve telemetry
- risk-on starter telemetry should begin recording evaluations when a quality failure matches an allowed starter reason

Historical `recent_errors` can remain in state until naturally replaced by newer telemetry; validation should focus on whether new recursion timestamps stop appearing after the redeploy.

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
- Existing paper-exposure position limits and breakout rotation policy remain available

## Prior Composition and X-Ray Versions

- `entry-pipeline-composition-guard-2026-07-14-v2-stable-stack`
- `entry-pipeline-xray-2026-07-14-v3-composition-errors`
- `usercustomize-entry-pipeline-composition-2026-07-14-v24-stable-watchdog`
- `one-test-policy-2026-07-14-entry-pipeline-composition-v3`

Prior key commits:

- `627bfeed8b1927a26a281a33ef3a38b446210bf3` — stable composition guard v2
- `9ba549feaa3eb0e28e23bd013157d7a391cc0376` — X-Ray v3 with error details and meaningful-cycle retention
- `06f7189179076f656642371250d613a90807c2e6` — stable startup/watchdog ordering
- `679cb4275177a0ff052cd428d6af3288f6e088c5` — prior completed handoff

## State and Reporting Notes

- X-Ray preserves both the latest cycle and the latest meaningful cycle.
- Historical recursion errors will remain visible in recent-error history until replaced; use timestamps to distinguish pre-fix from post-fix errors.
- The persistent TEM post-harvest row still reports `reason_not_available_in_state_snapshot`; this remains diagnostic debt rather than a risk/authority issue.
- Execution rows and observed outcomes previously moved backward in state. Continue watching for stale-state writes or reconciliation changes. Do not run repair routes unless a specific malformed-state condition is confirmed.

## Validation Procedure

After Railway redeploys, run:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- `overall: pass`
- `failed_required: []`
- no new warnings
- composition version is `entry-pipeline-composition-guard-2026-07-15-v3-recursion-safe`
- `direct_core_base: true`
- `recursion_safe: true`
- X-Ray remains patched and outermost
- positions, PnL, and risk state remain coherent

During the next open-market candidate cycle, verify that no new recursion errors are appended and that candidate results become entries, explicit blocker rows, or starter-valve evaluations.

Do not run mutating repair or execution endpoints as part of routine validation.
