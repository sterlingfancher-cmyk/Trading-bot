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

## Latest Runtime Evidence — July 21, 2026, 12:35:36 CDT

The first compact daily response successfully reduced payload size but exposed a source-extraction defect:

- `type: daily_self_check`
- `version: daily-self-check-compactor-2026-07-21-v1`
- `daily_response_compact: true`
- Entry pipeline remained healthy:
  - `current_callable: entry_pipeline_xray.wrapped`
  - `inner_callable: entry_pipeline_composition_guard.composed`
  - `stack_stable: true`
  - `direct_core_base: true`
  - `recursion_safe: true`
  - `participation_valve_chain_cycle_free: true`
- X-Ray invocations advanced to 85 while active-callsite errors remained at 10.
- The latest duplicate-reason TypeError remained historical at July 20, 12:01:39 CDT.
- Scanner and Phase 3A advisory fields remained visible.

However, critical compact fields were incorrectly null or zero:

- account equity, cash, PnL, wins/losses, and execution rows were null;
- open positions were incorrectly reported as zero;
- self-defense and drawdown fields were null;
- service status, checked paths, full diagnostics URL, and blocker coverage were missing.

This was a reporting-source problem only. It did not indicate that positions were closed or that account state was missing.

## Latest Code Update — Compact Daily Authoritative Fallbacks

### Root cause

The v1 compactor primarily read fields from `dashboard`, `truth_summary`, and `operator_summary`. Earlier wrappers can omit or replace those objects before the final compactor executes. The v1 fallback then used `len({})`, which silently converted a missing position source into `open_positions_count: 0`.

### Fix

Updated `daily_self_check_compactor.py` to version:

`daily-self-check-compactor-2026-07-21-v2-authoritative-fallbacks`

The compactor now:

1. Reads the authoritative runtime state using `core.load_state()` and falls back to `core.portfolio`.
2. Sources account fields from, in order:
   - compact status/performance snapshots;
   - truth/operator summaries;
   - persisted state performance;
   - persisted trade-journal summary;
   - direct state totals.
3. Sources position symbols from performance, persisted state, or status.
4. Never reports zero positions unless an actual position source is present and empty.
5. Sources self-defense and drawdown fields from status risk controls or persisted risk controls.
6. Sources scanner counts and blocker coverage from status, decision audit, blocker audit, or persisted scanner/audit state.
7. Always constructs the full diagnostics URL from the Railway base URL when the source payload omits it.
8. Reconstructs checked paths from result rows when needed.
9. Emits `compact_source_fields_missing` with an explicit list instead of silently returning critical null fields.
10. Unwraps any older compactor layer before installing v2 so wrappers do not accumulate after redeploy.

### Files changed

- `daily_self_check_compactor.py`
- `PROJECT_HANDOFF.md`

### Commits

- `33b9dc9bad6c69ed8e7e4daeb0df5a5d007939b4`
  - Added authoritative state/status/trade-journal fallbacks.
  - Prevented false zero-position reporting.
  - Added explicit missing-source warnings.
  - Guaranteed daily and full-diagnostics URLs.
- Handoff commit: the commit updating this file in the same work session.

### Routes

- Daily compact: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Full diagnostics: `https://trading-bot-clean.up.railway.app/paper/full-self-check`
- Compactor status: `https://trading-bot-clean.up.railway.app/paper/daily-self-check-compactor-status`

## Expected Runtime Evidence After Redeploy

The daily route should return:

- `type: daily_self_check`
- `version: daily-self-check-compactor-2026-07-21-v2-authoritative-fallbacks`
- `daily_response_compact: true`
- `source_fallbacks_used: true`
- `full_diagnostics_url: https://trading-bot-clean.up.railway.app/paper/full-self-check`
- populated `health.service`
- populated `account.equity` and `account.cash`
- position symbols and a correct non-fabricated `open_positions_count`
- populated realized/unrealized PnL and execution-row fields when present in state
- populated self-defense and drawdown fields
- populated scanner signal count
- blocker coverage when available in the persisted audit
- no `compact_source_fields_missing` warning when authoritative state is complete

The response must remain compact and must not restore the duplicated dashboard, full X-Ray history, complete rejected-signal arrays, complete blocker arrays, or result objects.

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
- `8557d89f91fbe786a974f4e0f4e930cf8c9b7eb7` — initial compact daily response

## State and Reporting Notes

- Historical X-Ray errors remain visible until aged out; compare timestamps and counters rather than treating an old row as a new failure.
- The persistent TEM post-harvest row with `reason_not_available_in_state_snapshot` remains diagnostic debt, not a risk/authority issue.
- Execution rows and observed outcomes have previously moved backward in state. Continue monitoring stale-state writes and reconciliation.
- Do not run repair routes unless a specific malformed-state condition is confirmed.

## Validation Procedure

After Railway redeploys, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm the v2 compact version, populated account/risk/health fields, accurate positions, full-diagnostics URL, stable entry pipeline, and no newly timestamped recursion or duplicate-reason error.

Use `/paper/full-self-check` only when the compact response reports `warn`/`fail`, a new error timestamp, or `compact_source_fields_missing`. Do not run mutating repair or execution endpoints during routine validation.
