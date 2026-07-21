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

## Latest Runtime Evidence — July 21, 2026, 12:19:41 CDT

The latest operator-supplied self-check passed:

- `overall: pass`
- `failed_required: []`
- Entry Pipeline X-Ray was outermost.
- `stack_stable: true`
- `direct_core_base: true`
- `recursion_safe: true`
- `participation_valve_chain_cycle_free: true`
- X-Ray invocations advanced to 84 while active-callsite errors remained at 10.
- The newest duplicate-reason TypeError remained historical at July 20, 12:01:39 CDT; no new occurrence was present.
- Self-defense was inactive.
- Equity: 10866.55
- Cash: 10111.46
- Open positions: DELL and QQQ
- Realized total: +733.97
- Unrealized PnL: +132.59
- Scanner signals: 42
- Market mode remained risk-off/bear in the latest meaningful scanner snapshot, so blocked long entries were appropriate.
- Phase 3A early paper advisory readiness was true, with live authority still off.

The remaining operator problem was response size: the routine self-check duplicated large X-Ray, blocker, dashboard, decision-audit, and operator-summary structures, making daily copy/paste impractical.

## Latest Code Update — Compact Daily Self-Check

### Purpose

Keep `/paper/self-check` as the single daily validation URL while reducing its response to operator-critical fields. Preserve the existing full diagnostic payload behind `/paper/full-self-check` for intentional troubleshooting.

### Implementation

Added `daily_self_check_compactor.py`.

For light/mobile-safe/daily mode it returns a compact payload containing:

- overall health and required failures;
- up to three current warnings;
- equity, cash, position symbols, PnL, wins/losses, and execution-row count;
- self-defense, daily-loss, and drawdown state;
- scanner signal/entry/rejection counts;
- post-harvest status;
- the top five blocker summaries only;
- blocker reason coverage and missing-detail count;
- entry-pipeline stability, recursion safety, direct-core status, helper-chain status, callable names, invocation/error counters, and only the latest error summary;
- starter-valve status;
- Phase 3A advisory readiness and one next action;
- a direct full-diagnostics URL.

The compactor does not remove or alter internal checks. The same diagnostic modules still run before the response is compacted. It only removes duplicated verbose structures from the returned daily JSON.

`usercustomize.py` now loads and reapplies the compactor after every other self-check promoter so later wrappers cannot expand the routine response again.

### Files changed

- `daily_self_check_compactor.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Versions

- `daily-self-check-compactor-2026-07-21-v1`
- `usercustomize-entry-pipeline-composition-2026-07-21-v27-daily-self-check-compact`
- Existing ownership guard: `entry-pipeline-ownership-guard-2026-07-20-v1`
- Existing composition: `entry-pipeline-composition-guard-2026-07-17-v4-valve-chain`
- Existing participation chain: `participation-valve-chain-2026-07-17-v1`
- Existing sanitizer: `starter-valve-reason-sanitizer-2026-07-20-v1`

### Commits

- `8557d89f91fbe786a974f4e0f4e930cf8c9b7eb7`
  - Added compact daily response builder and optional status route.
  - Preserves full diagnostics for non-light modes.
- `fdd59aea5b69fb8cc251589473a0eaab41361864`
  - Loads the compactor last at startup and during watchdog passes.
  - Adds compactor status to optional governance checks.
- Handoff commit: the commit updating this file in the same work session.

### Routes

- Daily compact: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Full diagnostics: `https://trading-bot-clean.up.railway.app/paper/full-self-check`
- Compactor status: `https://trading-bot-clean.up.railway.app/paper/daily-self-check-compactor-status`

## Expected Runtime Evidence After Redeploy

The daily route should return:

- `type: daily_self_check`
- `version: daily-self-check-compactor-2026-07-21-v1`
- `daily_response_compact: true`
- `full_diagnostics_url` populated
- compact sections named `health`, `account`, `risk`, `scanner`, `entry_pipeline`, `starter_valve`, and `ml`
- no duplicated `dashboard`, full X-Ray objects, complete rejected-signal arrays, complete blocker arrays, `results`, or verbose operator-summary structures

The full route should continue returning the complete diagnostic payload unchanged.

## Safety / Authority Impact

- Reporting-only change
- No internal check removed
- No threshold changes
- No sizing changes
- No scanner or candidate changes
- No order-placement changes
- No live authority added
- No ML authority added
- No cooldown bypass
- No self-defense bypass
- No risk-halt bypass
- No drawdown-control bypass
- No market-regime, futures-bias, trend, volume, relative-edge, extension, or quality bypass

## Current Runtime Stack

1. `entry_pipeline_xray` outer diagnostic wrapper
2. composition-owned paper-exposure overlay
3. direct closure over `core_entry_pipeline._core_try_entries_and_rotations`
4. clean base participation valve
5. extended-leader starter overlay
6. risk-on starter overlay
7. reason-safe blocker detail wrappers
8. ownership guard reassertion after other runtime modules
9. daily self-check compactor as the final reporting wrapper

## Prior Key Repairs

- `f3ecc3db1eebc0a645fd7806e54112ca4f660969` — entry-pipeline ownership and drift repair guard
- `fc002ce9a7daabcbcb951d298b7d0cc17c7da3ac` — duplicate-reason sanitizer
- `ac423cb488aaf0753340c88caab3f8114d80193e` — deterministic, cycle-free participation chain
- `daac00d02a969cde5fcbaa8c033a7be034bbc78a` — direct-core composition repair
- `9ba549feaa3eb0e28e23bd013157d7a391cc0376` — X-Ray v3 error and meaningful-cycle telemetry

## State and Reporting Notes

- Historical X-Ray errors remain visible until aged out; compare timestamps and counters rather than treating the presence of an old row as a new failure.
- The persistent TEM post-harvest row with `reason_not_available_in_state_snapshot` remains diagnostic debt, not a risk/authority issue.
- Execution rows and observed outcomes have previously moved backward in state. Continue monitoring stale-state writes and reconciliation.
- Do not run repair routes unless a specific malformed-state condition is confirmed.

## Validation Procedure

After Railway redeploys, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm the compact daily response, coherent account/risk state, stable entry pipeline, no newly timestamped recursion or duplicate-reason error, and the populated full-diagnostics URL.

Use `/paper/full-self-check` only when the compact response reports `warn`/`fail`, a new error timestamp, or missing critical fields. Do not run mutating repair or execution endpoints during routine validation.
