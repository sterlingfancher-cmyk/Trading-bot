# Automated Trading Project Handoff — Updated July 14, 2026

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

## Latest Known Runtime Evidence — July 14, 2026, 14:30:52 CDT

The operator supplied a passing self-check showing:

- `overall: pass`
- No required failures or warnings
- Equity: 11047.43
- Cash: 10018.25
- Open positions: DELL, QQQ, SNDK
- Realized PnL today: +106.26
- Unrealized PnL: +83.50
- Self-defense inactive
- Intraday drawdown: 0.118%
- X-Ray active-callsite invocations: 128
- X-Ray errors accumulated: 46
- X-Ray `new_entries_not_allowed`: 18
- X-Ray `no_candidates_or_no_action`: 64
- Active wrapped implementation before this repair: `paper_exposure_rotation.patched_try_entries_and_rotations`
- Core entry pipeline metadata before this repair: not authoritative / missing
- Risk-on starter valve telemetry: still no candidate evaluations

This proved the active runtime stack was composed incorrectly. `paper_exposure_rotation` was acting as the active replacement while the intended authoritative `core_entry_pipeline` path and its internal participation valve were not reliably in the live call chain.

## Completed Code Update — Stable Entry Pipeline Composition Repair

### Goal

Enforce this runtime stack:

1. `entry_pipeline_xray` as the outermost diagnostic wrapper
2. `paper_exposure_rotation` as a composable overlay
3. `core_entry_pipeline` as the authoritative implementation
4. `risk_on_starter_participation_valve` inside the core pipeline's participation helper

### Files changed

- `entry_pipeline_composition_guard.py`
- `entry_pipeline_xray.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Versions

- `entry-pipeline-composition-guard-2026-07-14-v2-stable-stack`
- `entry-pipeline-xray-2026-07-14-v3-composition-errors`
- `usercustomize-entry-pipeline-composition-2026-07-14-v24-stable-watchdog`
- Runtime one-test policy promotion: `one-test-policy-2026-07-14-entry-pipeline-composition-v3`

### Commits

- Initial interrupted composition-guard file landed before resume at repository commit shown by GitHub as `a29bf6a2811dba3142cec816092c5d0b2fe5cf24`.
- `627bfeed8b1927a26a281a33ef3a38b446210bf3`
  - Stabilized the composition guard.
  - Added a fast path that recognizes an already-correct X-Ray-over-composed stack and avoids rebuilding it every watchdog pass.
  - Forces `core_entry_pipeline` authoritative first.
  - Applies paper exposure as an overlay around the core callable.
  - Applies the risk-on starter valve to the core participation helper.
  - Persists composition status to state.
- `9ba549feaa3eb0e28e23bd013157d7a391cc0376`
  - Upgraded X-Ray to v3.
  - Calls the composition guard before wrapping the live call site.
  - Stores the wrapped original callable on the wrapper for safe unwrapping and composition checks.
  - Records recent exception type/message/callable metadata instead of only cumulative counters.
  - Preserves `last_meaningful_cycle`, `last_meaningful_stage_counts`, `last_meaningful_bottleneck`, symbol paths, and the last meaningful scanner audit so later empty cycles do not erase the useful session snapshot.
  - Keeps latest-cycle telemetry separately from meaningful-cycle telemetry.
- `ac357b869e3fdc700301f4e33ad43cf92acda893`
  - Added initial startup wiring for composition guard before X-Ray.
- `06f7189179076f656642371250d613a90807c2e6`
  - Corrected watchdog ordering so it does not call the core replacement on every pass.
  - The stable watchdog now reapplies only the idempotent extended-leader helper, composition guard, and outer X-Ray.
  - Lets the composition guard own core restoration and paper-exposure composition.
  - Prevents continuous stack rebuilding and reduces race risk during active cycles.
- `709779f588f35a67691f64be20d90adadf310673`
  - Recorded the completed repair and validation plan in the handoff.

### Routes

- Routine: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Composition: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-composition-status`
- X-Ray: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-xray-status`
- Risk-on starter valve: `https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status`
- Core pipeline: `https://trading-bot-clean.up.railway.app/paper/core-entry-pipeline-status`

## Expected Runtime Stack After Redeploy

The direct composition route should show:

- Version: `entry-pipeline-composition-guard-2026-07-14-v2-stable-stack`
- `stack_stable: true`
- Inner callable with:
  - `core_entry_pipeline_patched: true`
  - a populated `core_entry_pipeline_version`
  - `paper_exposure_version: entry-pipeline-composition-guard-2026-07-14-v2-stable-stack`
- Current callable should be the X-Ray wrapper after X-Ray registers.

The X-Ray route/self-check should show:

- Version: `entry-pipeline-xray-2026-07-14-v3-composition-errors`
- `patched: true`
- Patch target: `app.try_entries_and_rotations`
- Wrapped callable metadata showing the composed paper-exposure/core implementation
- `composition_status.stack_stable: true`
- `recent_errors` and `last_error` fields
- Latest-cycle fields
- Last-meaningful-cycle fields
- Preserved last meaningful scanner audit

After the next open-market cycle with signals, expected evidence includes:

- `telemetry_persisted: true`
- non-empty `last_meaningful_stage_counts`
- prepared candidates greater than zero when eligible signals are handed off
- quality-block rows that contain participation-valve details
- risk-on starter telemetry beginning to show candidate evaluations when quality fails for an allowed starter reason

## Safety / Authority Impact

- Composition and diagnostics only
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
- No trend/volume/relative-edge bypass
- Existing paper-exposure position limits and breakout rotation policy remain available, but now operate as an overlay around the authoritative core entry pipeline

## State and Reporting Notes

- X-Ray now preserves both the most recent cycle and the most recent meaningful cycle. A zero-signal late cycle should no longer erase the earlier useful signal-path evidence.
- Recent active-callsite exceptions now include actual error text and callable metadata.
- The persistent TEM row from `state.post_harvest_redeployment.top_candidates_reviewed` still reports `reason_not_available_in_state_snapshot`; this remains diagnostic debt rather than a risk/authority issue.
- Execution rows and ML observed outcomes previously moved backward in state. Continue watching for stale-state writes or reconciliation changes. Do not restore or repair state unless a specific malformed-state condition is confirmed.

## Validation Procedure

After Railway redeploys, run only the normal check first:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- `overall: pass`
- `failed_required: []`
- no new warnings
- `one_test_policy_version: one-test-policy-2026-07-14-entry-pipeline-composition-v3`
- X-Ray v3 is present
- composition status is present and stable
- current positions, PnL, and risk state remain coherent

Optional direct checks if the self-check lacks enough detail:

- `/paper/entry-pipeline-composition-status`
- `/paper/entry-pipeline-xray-status`

Do not run mutating repair or execution endpoints as part of validation.

## Current Next Action

Wait for Railway redeploy, then run `/paper/self-check`. During the next open-market cycle, inspect the X-Ray's last meaningful cycle, recent error messages, prepared-candidate count, quality-block count, participation-valve reach count, and symbol paths. Adjust only the proven blocker after the corrected core pipeline has accumulated fresh evidence.
