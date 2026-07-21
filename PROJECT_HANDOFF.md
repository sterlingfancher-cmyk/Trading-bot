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

## Latest Runtime Evidence — July 21, 2026, 12:43:56 CDT

The v2 authoritative fallbacks corrected account and risk truth:

- cash: 10111.46
- equity: 10864.08
- positions: DELL and QQQ
- open positions: 2
- realized total: +733.97
- unrealized PnL: +130.12
- execution rows: 83
- wins/losses: 34/16
- self-defense inactive
- intraday drawdown: 0.06%

The trading pipeline remained healthy:

- X-Ray outermost
- composition guard inner callable
- stable stack
- direct-core base active
- recursion safe
- participation chain cycle-free
- invocations advanced to 85 while active-callsite errors remained 10
- latest duplicate-reason TypeError remained historical at July 20, 12:01:39 CDT

The remaining defect was reporting order. Legacy promoters appended `dashboard`, full X-Ray, decision-audit, operator-summary, and starter-summary objects after compaction. Some compact fields also read incomplete intermediate sources, and scanner counts mixed decision-audit and blocker-audit snapshots.

## Latest Code Update — Terminal Daily Serializer

### Root cause

A function wrapper was not a strong enough final boundary. Runtime modules could still wrap or mutate `self_check.run_self_check` after the compactor, restoring verbose structures or leaving compact fields sourced from incomplete intermediate objects.

### Fix

Updated `daily_self_check_compactor.py` to:

`daily-self-check-compactor-2026-07-21-v3-terminal-serializer`

The daily check is now a route-level terminal serializer:

1. Flask's `paper_self_check` and `paper_smoke_test` view functions are replaced directly.
2. The terminal view calls the unwrapped `self_check.run_mobile_self_check()` builder rather than the shared wrapper chain.
3. A brand-new dictionary is returned from an explicit allowlist; no source payload is mutated or merged.
4. Verbose keys such as `dashboard`, `operator_summary`, full X-Ray history, full decision audit, complete blocker arrays, and endpoint result arrays cannot survive serialization.
5. Pipeline status falls back directly to `entry_pipeline_xray.status_payload()`.
6. Starter-valve status falls back directly to `risk_on_starter_participation_valve.status_payload()`.
7. Decision/ML status falls back directly to `decision_audit_consolidation.build_payload()`.
8. Blocker summaries fall back directly to `blocked_entry_reason_audit.status_payload()`.
9. Scanner counts are source-labelled:
   - `signals_found` uses decision audit;
   - `blocker_audit_signals_found` is reported separately;
   - `source_mismatch` identifies non-aligned snapshots instead of silently mixing them.
10. Critical account, risk, pipeline, starter, and ML fields are validated before return. Missing fields produce `compact_source_fields_missing` and elevate status to warn.
11. The output includes `terminal_compaction_applied: true`.

Updated `usercustomize.py` to:

`usercustomize-entry-pipeline-composition-2026-07-21-v28-terminal-daily-serializer`

The watchdog now reasserts the terminal Flask route after every other runtime module, not merely a final function wrapper.

### Files changed

- `daily_self_check_compactor.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Commits

- `06e0bc313f1be33502105707676f1fe90371c269`
  - Added terminal route serializer, explicit allowlist, direct module fallbacks, critical-field validation, and source-labelled scanner counts.
- `06a6ba1392e3214aea5bcb52ec98667b82125cc0`
  - Reasserts the terminal daily Flask view after all runtime modules.
- Handoff commit: the commit updating this file in the same work session.

## Expected Daily Response After Redeploy

The daily route should include only these top-level sections/fields:

- `status`
- `overall`
- `type`
- `version`
- `generated_local`
- `daily_response_compact`
- `terminal_compaction_applied`
- `source_fallbacks_used`
- `full_diagnostics_url`
- `routine_test_url`
- `health`
- `account`
- `risk`
- `scanner`
- `entry_pipeline`
- `starter_valve`
- `ml`
- `note`

Required identity fields:

- `type: daily_self_check`
- `version: daily-self-check-compactor-2026-07-21-v3-terminal-serializer`
- `daily_response_compact: true`
- `terminal_compaction_applied: true`

The following must not appear:

- `dashboard`
- `operator_summary`
- `decision_audit_summary`
- `entry_pipeline_xray_summary`
- `risk_on_starter_participation_summary`
- complete rejected-signal arrays
- full recent-error arrays
- endpoint `results`

Expected populated compact fields include account truth, risk controls, pipeline stability/callable names, starter-valve status, Phase 3A advisory status, and the full-diagnostics URL.

## Safety / Authority Impact

- Reporting-only change
- No internal risk check removed
- No threshold changes
- No sizing changes
- No scanner/candidate changes
- No order-placement changes
- No live authority added
- No ML authority added
- No cooldown, self-defense, risk-halt, drawdown, regime, trend, volume, relative-edge, extension, quality, or futures-bias bypass

## Current Runtime Stack

1. `entry_pipeline_xray` outer diagnostic wrapper
2. composition-owned paper-exposure overlay
3. direct closure over `core_entry_pipeline._core_try_entries_and_rotations`
4. clean base participation valve
5. extended-leader starter overlay
6. risk-on starter overlay
7. reason-safe blocker detail wrappers
8. entry-pipeline ownership guard reassertion
9. terminal daily route serializer reassertion

## Validation Procedure

After Railway redeploys, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm:

- v3 terminal serializer identity fields;
- no verbose structures outside the compact allowlist;
- populated account, risk, pipeline, starter, and ML fields;
- `scanner.signal_count_source: decision_audit`;
- stable pipeline and no newly timestamped recursion or duplicate-reason error.

Use `/paper/full-self-check` only for warn/fail, a new error timestamp, or `compact_source_fields_missing`. Do not run mutating repair or execution endpoints during routine validation.
