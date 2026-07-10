# Automated Trading Project Handoff — Updated July 10, 2026

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

## Latest Known Good State — July 10, 2026, 12:55:50 CDT

- Self-check: pass
- Status: ok
- Failed required: none
- Warnings: none
- Elapsed: 84.72 ms
- Cash/equity: 11075.54
- Open positions: 0
- Realized today: -1.46
- Realized total: +1075.56
- Unrealized PnL: 0.0
- Daily/intraday drawdown: 0.055%
- Self-defense: inactive
- Signals found: 46
- Execution rows: 88 / 150
- ML rows: 6000
- ML labeled rows: 1864
- ML observed outcomes: 55
- ML predictions: 25
- Early paper Phase 3A ready: true

## Latest Code Update — Entry Pipeline X-Ray

### Purpose

Multiple sessions produced dozens of scanner signals but zero entries. Risk-on starter telemetry confirmed the valve was installed and patched, but no valve evaluations were persisted. The remaining question was where candidates disappeared before reaching `core_entry_pipeline._participation_valve_ok`.

The Entry Pipeline X-Ray adds stage-by-stage and per-symbol telemetry around the entire core entry function without modifying trading behavior.

### Files changed

- `entry_pipeline_xray.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Versions

- `entry-pipeline-xray-2026-07-10-v1`
- `usercustomize-entry-pipeline-xray-2026-07-10-v22`
- One-test policy is promoted at runtime to `one-test-policy-2026-07-10-entry-pipeline-xray`

### Commits

- `ef8c4796ae56fe5d9efdf72b8dbda81c2e638215`
  - Added `entry_pipeline_xray.py`.
  - Wraps `core_entry_pipeline._core_try_entries_and_rotations` for observation only.
  - Records raw long/short signal counts, prepared candidate count, entries, rotations, blocked rows, quality blocks, participation-valve reachability, candidates without final rows, bottleneck classification, top rejection reasons, and per-symbol paths.
  - Persists telemetry under `state["entry_pipeline_xray"]`.
  - Adds `/paper/entry-pipeline-xray-status`.
  - Promotes compact X-Ray telemetry into `/paper/self-check` through the existing one-test postprocessor.
- `ab32cff7481face14a0641f3b09d42bc79a534a6`
  - Wired `entry_pipeline_xray` into `usercustomize.py` after `risk_on_starter_participation_valve`.
  - Added the route to optional one-test governance metadata.
  - Added watchdog re-registration.

### Telemetry fields

The X-Ray records:

- `raw_long_signals`
- `raw_short_signals`
- `raw_total_signals`
- `prepared_candidates`
- `core_entries_returned`
- `core_rotations_returned`
- `core_blocked_rows_returned`
- `quality_blocked_rows`
- `participation_valve_reached_rows`
- `candidates_without_final_row`
- `bottleneck`
- `top_rejection_reasons`
- `symbol_paths`
- recent cycle counters

Per-symbol paths identify whether a candidate:

- entered as an input signal;
- became a prepared candidate;
- reached core pipeline review;
- reached the participation valve;
- returned an entry;
- returned a blocked row; or
- disappeared without a final visible row.

### Bottleneck classifications

- `new_entries_not_allowed`
- `candidate_preparation`
- `core_pipeline_no_final_rows`
- `before_entry_quality_or_valve`
- `quality_block_not_reaching_valve`
- `participation_valve_or_enter_position`
- `entries_returned`
- `none`

### Routes

- Routine: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Direct X-Ray: `https://trading-bot-clean.up.railway.app/paper/entry-pipeline-xray-status`
- Risk-on valve: `https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status`

### Safety / authority impact

- Diagnostic only
- Does not change signals or candidates
- Does not change thresholds
- Does not change sizing
- Does not place trades
- Does not change live authority
- Does not change ML authority
- Does not bypass cooldowns, self-defense, risk halts, drawdown controls, trend/volume checks, or entry-quality controls

### Post-redeploy expectations

Run `/paper/self-check` after Railway redeploys.

Expected:

- `overall: pass`
- `failed_required: []`
- `one_test_policy_version: one-test-policy-2026-07-10-entry-pipeline-xray`
- `dashboard.entry_pipeline_xray` present
- `entry_pipeline_xray_summary` present
- `operator_summary.entry_pipeline_xray_*` fields present

The direct route should show:

- `status: ok`
- `patched: true`
- `version: entry-pipeline-xray-2026-07-10-v1`
- `telemetry_persisted: true` after a fresh entry cycle
- last stage counts, bottleneck, rejection reasons, and symbol paths

If telemetry is present but no cycle has run yet, allow the next scanner/entry cycle to complete and check again.

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

Prior July 10 validation showed:

- enabled: true
- patched: true
- telemetry persisted: false
- recent evaluations: empty
- last reason/symbol/status: null

That result motivated the upstream Entry Pipeline X-Ray.

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
2. Use `/paper/entry-pipeline-xray-status` only when inspecting the entry bottleneck.
3. Do not run repair or execution routes unless intentionally required.
4. Do not loosen entry/risk thresholds until X-Ray telemetry identifies the actual stage reducing candidates to zero.
5. Keep live ML authority off until strict benchmark and walk-forward/MAE-MFE validation support stronger authority.

## Next Action

After Railway redeploys, run the normal self-check. If X-Ray telemetry shows `before_entry_quality_or_valve`, `candidate_preparation`, or `core_pipeline_no_final_rows`, inspect that specific upstream path. If it shows `participation_valve_or_enter_position`, use the persisted symbol paths and rejection reasons to adjust only the proven bottleneck. Do not broadly loosen the system before this evidence is available.
