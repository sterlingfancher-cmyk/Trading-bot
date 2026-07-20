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

## Latest Runtime Evidence — July 20, 2026, 12:20:38 CDT

The operator supplied a passing self-check. The deterministic valve chain was active and cycle-free, and no new recursion errors were present. Meaningful entry cycles were instead failing with a new reporting-layer exception:

- `overall: pass`
- `failed_required: []`
- Composition version: `entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- Participation chain: `participation-valve-chain-2026-07-17-v1`
- `participation_valve_chain_cycle_free: true`
- `recursion_safe: true`
- X-Ray active-callsite errors: 10
- Repeated exception through 12:01:39 CDT: `_patched_participation_valve_ok.<locals>.blocked() got multiple values for argument 'reason'`
- Risk-on starter telemetry remained empty because the exception occurred before a blocker result could be persisted
- Market mode during the latest scanner snapshot: `crash_warning`
- Risk score: 17
- Open positions: DELL, QQQ, SNDK
- Equity: 10837.88
- Cash: 9672.49
- Unrealized PnL: -19.78
- Total realized PnL: +857.68

## Latest Code Update — Starter Valve Reason Sanitizer

### Root cause

Both starter overlays use a local helper shaped like:

`blocked(reason, **extra)`

Some call sites passed:

`blocked(info.get("reason", fallback), **info)`

When `info` was a normal dictionary containing its own `reason` key, Python received `reason` once positionally and once through keyword expansion, raising `TypeError`.

Affected paths:

- `risk_on_starter_participation_valve._quality_block_allowed`
- `risk_on_starter_participation_valve._risk_ok`
- `extended_leader_starter_valve._risk_ok`

### Fix

Added `starter_valve_reason_sanitizer.py`.

The sanitizer wraps the three tuple-returning helper functions and converts blocker-detail dictionaries into a reason-safe mapping:

- `mapping.get("reason")` still returns the original reason for the positional argument.
- The `reason` key is absent from mapping expansion, so `**mapping` cannot pass it a second time.
- All other detail fields remain available for telemetry.
- No decision rule, threshold, sizing factor, or authority setting is changed.

`usercustomize.py` now loads and reapplies the sanitizer immediately after deterministic entry-stack composition and before X-Ray remains outermost.

### Files changed

- `starter_valve_reason_sanitizer.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Versions

- `starter-valve-reason-sanitizer-2026-07-20-v1`
- `usercustomize-entry-pipeline-composition-2026-07-20-v25-reason-sanitizer`
- Existing composition remains `entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- Existing helper chain remains `participation-valve-chain-2026-07-17-v1`

### Commits

- `fc002ce9a7daabcbcb951d298b7d0cc17c7da3ac`
  - Added reason-safe mapping and helper wrappers.
  - Prevents duplicate `reason` keyword expansion in both starter overlays.
- `536b5dbd4704e8ad6dcc7a502632069df3a607d5`
  - Loads the sanitizer after composition.
  - Reapplies it from the watchdog entry-stack repair path.
  - Adds optional sanitizer status route to self-check governance endpoints.
- Handoff commit: the commit that updates this file in the same work session.

### Routes

- Routine: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Sanitizer: `https://trading-bot-clean.up.railway.app/paper/starter-valve-reason-sanitizer-status`
- Composition: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-composition-status`
- X-Ray: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-xray-status`
- Risk-on starter valve: `https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status`

## Expected Runtime Evidence After Redeploy

Routine self-check should show:

- `overall: pass`
- `failed_required: []`
- composition remains v4 and cycle-free
- sanitizer version `starter-valve-reason-sanitizer-2026-07-20-v1`
- `duplicate_reason_kwarg_prevented: true`
- `logic_changed: false`
- `authority_changed: false`

After a fresh meaningful candidate cycle:

- no new `TypeError` with `multiple values for argument 'reason'`
- active-callsite error counter should stop increasing from this exception
- prepared candidates should return entries or explicit blocked rows
- participation-valve telemetry should record blocked or allowed evaluations when candidates reach the helper
- bear/crash-warning candidates should be cleanly blocked by risk controls rather than terminated by an exception

Historical X-Ray errors may remain until replaced; compare timestamps and counters after redeploy.

## Safety / Authority Impact

- Reporting/argument-sanitization repair only
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

## Current Runtime Stack

1. `entry_pipeline_xray` outer diagnostic wrapper
2. `paper_exposure_rotation` overlay
3. direct closure over `core_entry_pipeline._core_try_entries_and_rotations`
4. clean base participation valve
5. extended-leader starter overlay
6. risk-on starter overlay
7. reason-safe blocker detail wrappers on overlay helper results

## Prior Key Repairs

- `ac423cb488aaf0753340c88caab3f8114d80193e` — deterministic, cycle-free base -> extended -> risk-on participation chain
- `daac00d02a969cde5fcbaa8c033a7be034bbc78a` — direct-core outer composition repair
- `9ba549feaa3eb0e28e23bd013157d7a391cc0376` — X-Ray v3 with error details and meaningful-cycle retention
- `06f7189179076f656642371250d613a90807c2e6` — stable startup/watchdog ordering

## State and Reporting Notes

- X-Ray preserves both the latest cycle and latest meaningful cycle.
- Historical recursion and TypeError records remain visible until replaced; use timestamps to distinguish pre-fix and post-fix errors.
- The persistent TEM post-harvest row still reports `reason_not_available_in_state_snapshot`; this remains diagnostic debt rather than a risk/authority issue.
- Execution rows and observed outcomes have previously moved backward in state. Continue watching for stale-state writes or reconciliation changes. Do not run repair routes unless a specific malformed-state condition is confirmed.

## Validation Procedure

After Railway redeploys, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm service health, sanitizer presence, cycle-free composition, coherent positions/PnL/risk state, and no newly timestamped duplicate-reason TypeError after the next meaningful candidate cycle.

Do not run mutating repair or execution endpoints as part of routine validation.
