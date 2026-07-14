# Automated Trading Project Handoff — Updated July 13, 2026

## Standing Rule

Every future code/configuration update must also update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine test: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Early paper Phase 3A guarded-advisory mode: active
- Strict stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## Latest Known Good State — July 13, 2026, 19:51:01 CDT

- Self-check: pass
- Status: ok
- Failed required: none
- Warnings: none
- Elapsed: 80.99 ms
- Cash/equity: 11061.58
- Open positions: 0
- Realized today: -5.22
- Realized total: +1061.60
- Unrealized PnL: 0.0
- Daily/intraday drawdown: 0.168%
- Self-defense: inactive
- Signals found: 54
- Scanner blocked entries: 120
- Decision-audit blocked entries: 1
- Execution rows: 88 / 150
- ML rows: 6000
- ML labeled rows: 1892
- ML observed outcomes: 55
- ML predictions: 25
- Early paper Phase 3A ready: true

## Latest Finding — Original X-Ray Did Not Observe Active Cycles

The July 13 after-hours self-check confirmed:

- `entry-pipeline-xray-2026-07-10-v1` was patched.
- `entry_pipeline_xray.telemetry_persisted` was false.
- Stage counts, symbol paths, bottleneck, and counters were empty.
- Risk-on starter telemetry was also patched but still had no evaluations.
- The scanner found 54 signals and persisted 120 scanner blocker rows.

Inspection of `app.py` confirmed the real runtime path:

1. `run_cycle()` calls `scan_signals(market)`.
2. It computes opening/risk/self-defense entry blockers.
3. It calls the global `app.try_entries_and_rotations(...)` callable directly.
4. The result is written into scanner audit and state.

The first X-Ray wrapped `core_entry_pipeline._core_try_entries_and_rotations`, which is an internal helper. Runtime patch order can replace or bypass that helper wrapper while `app.try_entries_and_rotations` remains the function actually invoked by `run_cycle()`.

## Latest Code Update — Active Call-Site Entry Pipeline X-Ray v2

### Purpose

Instrument the exact callable used by `run_cycle()` so every market-cycle scanner-to-entry handoff is observed regardless of which entry implementation or overlay is active.

### File changed

- `entry_pipeline_xray.py`
- `PROJECT_HANDOFF.md`

### Version

- `entry-pipeline-xray-2026-07-13-v2-active-callsite`
- Runtime one-test policy promotion: `one-test-policy-2026-07-13-entry-pipeline-active-callsite`

### Commit

- `91551026f10effbf324dba0feff7aa8112b5c85e`
  - Replaced the internal-helper-only X-Ray with a wrapper around `app.try_entries_and_rotations`.
  - Records the actual wrapped callable metadata, including whether the underlying callable is the core-entry non-wrapper replacement.
  - Passes arguments and return values through unchanged.
  - Persists telemetry even when the wrapped callable raises, then re-raises the original exception.

### Exact telemetry now recorded

- Patch target: `app.try_entries_and_rotations`
- Wrapped callable name/module/version metadata
- Raw long signals
- Raw short signals
- Total scanner signals handed into the active entry callable
- Active call-site invocation count
- Prepared candidates
- Entries returned
- Rotations returned
- Blocked rows returned
- Quality-blocked rows
- Participation-valve reached rows
- Candidates without a final visible row
- Per-symbol stage paths
- Top rejection reasons
- Entry-block reason
- Market mode
- Whether longs/shorts were allowed
- Exceptions from the active callable
- Recent cycles and bottleneck counters

### New per-symbol path format

Examples:

- `scanner_signal -> run_cycle_handoff -> active_try_entries_call -> prepared_candidate -> entry_pipeline_reviewed -> participation_valve_reached -> blocked`
- `scanner_signal -> run_cycle_handoff -> active_try_entries_call -> prepared_candidate -> entry_pipeline_reviewed -> entry_returned`
- `scanner_signal -> run_cycle_handoff -> active_try_entries_call -> prepared_candidate -> no_final_row_visible`

### Bottleneck classifications

- `active_callsite_error`
- `new_entries_not_allowed`
- `candidate_preparation`
- `active_pipeline_no_final_rows`
- `before_quality_or_participation_valve`
- `quality_block_not_reaching_participation_valve`
- `participation_valve_or_enter_position`
- `entries_returned`
- `no_candidates_or_no_action`

### Routes

- Routine: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Direct X-Ray: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-xray-status`
- Risk-on valve: `https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status`

### Safety / authority impact

- Diagnostic only
- Does not change candidate lists
- Does not change thresholds
- Does not change sizing
- Does not place trades
- Does not change the wrapped callable return value
- Does not change live authority
- Does not change ML authority
- Does not bypass cooldowns, self-defense, risk halts, drawdown controls, trend/volume checks, or entry-quality controls

## Post-Redeploy Expectations

Run the normal self-check after Railway redeploys:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Expected immediately:

- `overall: pass`
- `failed_required: []`
- X-Ray version: `entry-pipeline-xray-2026-07-13-v2-active-callsite`
- Patch target: `app.try_entries_and_rotations`
- Current callable metadata should show the X-Ray wrapper.
- Wrapped callable metadata should identify the underlying active entry implementation.

Expected after the next open-market cycle:

- `telemetry_persisted: true`
- `active_callsite_invocations` at least 1
- Non-empty `last_stage_counts`
- A concrete `last_bottleneck`
- Non-empty symbol paths whenever scanner signals were passed into the entry callable

If telemetry remains empty after an open-market cycle, inspect whether `run_cycle()` itself is being replaced or whether the auto-runner is executing a different module/process. That would be the next and narrower runtime-path issue.

## Risk-On Starter Valve Status

Current version:

- `risk-on-starter-participation-valve-2026-07-09-v3-telemetry`

Current policy:

- Paper only
- Max one starter per day and one per cycle
- Allocation factor 0.18
- Minimum cash 85%
- Minimum raw score 0.008
- Minimum rank score 0.012
- Allowed market modes: constructive and risk_on
- Live authority none
- Hard safety blockers remain authoritative

The starter valve has been patched but has not yet persisted a candidate evaluation. Active call-site X-Ray v2 should determine whether candidates reach the core pipeline and whether quality-block rows contain participation-valve details.

## Other Critical Current Modules

- Early paper ML Phase 3A gate: `ml-phase3a-early-paper-gate-2026-07-02-v1`
- Dynamic universe startup fix: `dynamic-universe-builder-2026-07-01-v4-source-symbol-hygiene`
- Blocked-entry audit: `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup`
- Blocked-entry self-check overlay: `blocked-entry-reason-selfcheck-overlay-2026-06-30-v3-placeholder-cleanup`
- Controlled redeployment starter sleeve: `controlled-redeployment-starter-sleeve-2026-06-30-v2-borderline-quality-review`

## Known Diagnostic Debt

- Persistent TEM row from `state.post_harvest_redeployment.top_candidates_reviewed` still reports `reason_not_available_in_state_snapshot`.
- This is reporting debt, not a trading-authority or risk failure.

## Operating Guidance

1. Use `/paper/self-check` for routine post-push validation.
2. Use `/paper/entry-pipeline-xray-status` only for detailed entry-path inspection.
3. Do not run repair or execution routes unless intentionally required.
4. Do not loosen entry/risk thresholds until active-call-site X-Ray telemetry identifies the actual stage reducing candidates to zero.
5. Keep live ML authority off until strict benchmark and walk-forward/MAE-MFE validation support stronger authority.

## Next Action

After Railway redeploys, run `/paper/self-check`. After the next open-market auto-run cycle, inspect `entry_pipeline_xray_summary`. The expected result is a concrete stage count and bottleneck from the exact `app.try_entries_and_rotations` call used by `run_cycle()`. Adjust only the proven bottleneck after that evidence is available.
