# Automated Trading Project Handoff — Updated July 10, 2026

## Standing Update Rule

Every future code/configuration update must also update this `PROJECT_HANDOFF.md` file in the same work session. The handoff entry should include files changed, new module/version strings, commits, routes affected, authority/safety impact, Railway post-redeploy check result or exact endpoints still needing verification, and next recommended action.

This rule exists so the project can be resumed from GitHub without relying on chat history.

## Current System Status

Base app URL:

https://trading-bot-clean.up.railway.app

GitHub repo:

sterlingfancher-cmyk/Trading-bot

Current operating mode:

- Paper trading only.
- Live trade authority: none.
- ML live authority: none.
- Early paper Phase 3A guarded-advisory mode: active and confirmed in the July 10 afternoon self-check.
- Risk-on starter participation valve: v3 telemetry is deployed and visible inside `/paper/self-check`.
- Risk-on starter telemetry conclusion from July 10: `patched: true`, version is v3, but `telemetry_persisted: false`, `recent_evaluations: []`, and all last-evaluation fields are null; candidate flow still has not reached the valve evaluation path.
- Strict Phase 3A / stronger authority benchmark: still 150 execution rows and 100 observed outcomes.
- Routine test link: https://trading-bot-clean.up.railway.app/paper/self-check
- Optional risk-on starter valve route: https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status
- Do not use heavy diagnostic routes unless intentionally debugging.
- Do not run repair routes unless a specific state issue appears.
- Do not run execution routes after hours.
- Do not run mutating Railway endpoints during routine post-push checks.

Latest known good routine self-check supplied by operator on July 10, 2026 at 12:55:50 CDT showed:

- Overall: pass.
- Status: ok.
- Failed required: none.
- Warnings: none.
- Elapsed time: 84.72 ms.
- One-test policy version: `one-test-policy-2026-07-09-risk-on-starter-telemetry`.
- Checked internal paths: /health and /paper/status.
- Persistent storage configured: true.
- State file: /data/state.json.
- State size: 15,175,326 bytes.
- Trades count: 88.
- Execution rows: 88 / 150.
- Cash: 11075.54.
- Equity: 11075.54.
- Open positions: 0.
- Realized today: -1.46.
- Realized total: +1075.56.
- Unrealized PnL: 0.0.
- Wins today: 0.
- Wins total: 39.
- Losses today: 1.
- Losses total: 16.
- Daily loss pct: 0.055.
- Intraday drawdown pct: 0.055.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.
- Scanner signals found: 46.
- Scanner-audit blocked entries: 0.
- Decision-audit blocked entries: 0.
- ML rows: 6000.
- ML labeled rows: 1864.
- ML observed outcomes: 55.
- ML predictions: 25.
- Early paper Phase 3A ready: true.
- Live ML authority: false / none.

## Latest Verification — July 10, 2026 Afternoon Self-Check

The operator supplied a successful `/paper/self-check` payload at 2026-07-10 12:55:50 CDT after the v3 risk-on starter telemetry update.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `summary_counts`: pass 2, fail 0, warn 0, linked_only 3.
- `/paper/self-check` returned quickly with `elapsed_ms: 84.72`.
- Checked paths were `/health` and `/paper/status` using direct state snapshots.
- `one_test_policy_version`: `one-test-policy-2026-07-09-risk-on-starter-telemetry`.
- Mobile-safe mode remains active.

Risk-on starter telemetry validation:

- `/paper/self-check` now includes `dashboard["risk_on_starter_participation"]` and `risk_on_starter_participation_summary`.
- Operator summary now includes `risk_on_starter_*` fields.
- `risk_on_starter_version`: `risk-on-starter-participation-valve-2026-07-09-v3-telemetry`.
- `risk_on_starter_status`: ok.
- `risk_on_starter_enabled`: true.
- `risk_on_starter_patched`: true.
- `risk_on_starter_telemetry_persisted`: false.
- `risk_on_starter_recent_evaluations`: empty.
- `risk_on_starter_counters`: empty.
- `risk_on_starter_last_status`: null.
- `risk_on_starter_last_reason`: null.
- `risk_on_starter_last_symbol`: null.
- `risk_on_starter_last_bucket`: null.
- `risk_on_starter_last_score`: null.
- `risk_on_starter_last_rank_score`: null.
- `risk_on_starter_last_rank_index`: null.
- Policy summary still shows paper-only, live authority none, max one entry per day, max one entry per cycle, allocation factor 0.18, minimum cash pct 85.0, min raw score 0.008, min rank score 0.012, and preferred leadership buckets.

Interpretation of telemetry:

- The v3 telemetry deployment worked: self-check is exposing the valve status and operator-summary fields.
- The valve is enabled and patched.
- No valve candidate evaluation has persisted yet.
- Therefore, the current missed-participation question is probably upstream of the valve: candidates are likely being blocked before reaching `core_entry_pipeline._participation_valve_ok`, or the scan/status snapshot is not from a cycle where that helper was invoked.
- Do not loosen v3 from this snapshot.
- The next code change should instrument upstream candidate routing into the core entry pipeline, not change risk/entry thresholds.

Portfolio / risk status:

- Equity: 11075.54.
- Cash: 11075.54.
- Open positions: 0.
- Realized today: -1.46.
- Realized total: +1075.56.
- Unrealized PnL: 0.0.
- Wins today: 0.
- Losses today: 1.
- Daily loss pct: 0.055.
- Intraday drawdown pct: 0.055.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.

Blocked-entry diagnostic status:

- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` remains live.
- `blocked_entries_count`: 0 in scanner audit / 0 in decision audit.
- `signals_found`: 46.
- `visible_blocked_rows_count`: 29.
- `actionable_reason_coverage_pct`: 96.55.
- `rows_with_actionable_reason`: 28.
- `rows_missing_reason_detail`: 1.
- Remaining missing row is still TEM from `state.post_harvest_redeployment.top_candidates_reviewed` with `reason_not_available_in_state_snapshot`.
- Top blocker category: `extension_chase` with 15 rows.
- Other categories: `quality_score` 13 rows and `reason_detail_missing` 1 row.
- Top reasons included `extended_below_5m_ma20` 15 rows, `score_below_post_harvest_floor` 12 rows, one futures-bias opening-long block, and one persistent TEM missing-reason row.

Top visible blocked symbols during this check:

- PANW
- WULF
- CLSK
- CORZ
- TEM
- ARM
- ALAB
- PLTR
- CRWD
- AAOI
- IREN
- CIFR
- MARA
- BTDR
- APLD
- SOUN
- WGMI
- HUT
- UCTT
- IESC

Watched momentum symbols:

- Blocked: BTDR, CIFR, CLSK, CORZ, HUT, IREN, MARA, PL, WULF.
- Seen: AMD, ASTS, AVGO, BKSY, BTDR, CIFR, CLSK, CORZ, DELL, GEV, HIVE, HUT, IREN, LRCX, LUNR, MARA, MU, NBIS, NVTS, PL, RDW, RIOT, RKLB, SPCX, STX, TER, WDC, WULF.

Operational interpretation:

- No repair is required for health/risk.
- The system is healthy, fast, and passing routine checks.
- The bot is flat in cash and self-defense is inactive.
- The small realized loss today is negligible relative to account equity and did not trigger risk controls.
- Early paper Phase 3A remains active with live authority off.
- The v3 telemetry surface is now working in self-check, but it shows no valve evaluations yet.
- Do not loosen thresholds or expand allowed risk-on starter behavior from this snapshot.
- Next diagnostic should identify why candidates with extension/score-floor blockers are not reaching the risk-on starter valve evaluation path.
- Next separate cleanup remains TEM post-harvest reason persistence so the final `reason_not_available_in_state_snapshot` row goes to zero.

## Latest Code Update — July 9, 2026: Risk-On Starter Valve Telemetry v3

### Reasoning

The July 9 direct `/paper/risk-on-starter-participation-status` check proved the risk-on starter valve v2 was deployed and patched, but its `latest` field was empty. That meant the missed FVG/reclaim participation could not be blamed on the module being absent. The unresolved question was whether candidates were reaching the valve and, if they were, which exact gate blocked them: market context, preferred bucket/symbol policy, rank/score, cash/risk, allowed-block-token matching, hard blocker, or daily/cycle cap.

The correct next step was telemetry, not loosening risk.

### Files changed

- `risk_on_starter_participation_valve.py`
- `one_link_check.py`
- `PROJECT_HANDOFF.md`

### New versions

- `risk-on-starter-participation-valve-2026-07-09-v3-telemetry`
- `one-test-policy-2026-07-09-risk-on-starter-telemetry`

### Commits

- `bafea813541fda56a6d83ff448456bb11d9c1ebb`
  - Updated `risk_on_starter_participation_valve.py` to v3 telemetry.
  - Persists every valve evaluation into state under `state["risk_on_starter_participation_valve"]`.
  - Persists `last_status`, `last_reason`, `last_symbol`, `last_bucket`, `last_evaluation`, `recent_evaluations`, and counters.
  - Captures candidate fields: symbol, bucket, side, rank index, score, rank score, cash percentage, open position count, quality reason, prior participation-valve reason, matched allowed tokens, hard block tokens, and risk-context payload.
  - Direct route exposes persisted `state_telemetry`, `last_evaluation`, `last_status`, `last_reason`, `recent_evaluations`, `counters`, and `telemetry_persisted`.
  - Does not change entry thresholds, allocation, allowed blockers, hard blockers, live authority, ML authority, or trade execution behavior.
- `7d88a9dcf9c0b56bf2fe05dff07fb91dec22e100`
  - Updated `one_link_check.py` so `/paper/self-check` promotes risk-on starter telemetry into `dashboard["risk_on_starter_participation"]` and `risk_on_starter_participation_summary`.
  - Adds operator summary fields including `risk_on_starter_status`, `risk_on_starter_version`, `risk_on_starter_enabled`, `risk_on_starter_patched`, `risk_on_starter_telemetry_persisted`, `risk_on_starter_last_status`, `risk_on_starter_last_reason`, `risk_on_starter_last_symbol`, `risk_on_starter_last_bucket`, `risk_on_starter_last_score`, `risk_on_starter_last_rank_score`, `risk_on_starter_last_rank_index`, `risk_on_starter_last_prior_reason`, matched/hard-block tokens, counters, and recent evaluations.
  - Adds `/paper/risk-on-starter-participation-status` to one-test metadata as a safe optional governance endpoint.
- `2e9a1267fc5cf27863e8eca430bc84a81a6e4acf`
  - Updated handoff with v3 telemetry implementation and expected checks.

### Routes affected

- `/paper/risk-on-starter-participation-status`
- `/paper/self-check`

### Safety / authority impact

- Diagnostic telemetry only.
- Paper-only behavior preserved.
- Live trade authority remains none.
- ML live authority remains none.
- Does not place trades directly.
- Does not wrap the main entry loop beyond the existing participation-valve helper patch.
- Does not lower thresholds.
- Does not change allocation factor.
- Does not add buckets/symbols.
- Does not bypass cooldowns, self-defense, risk halts, daily-loss, intraday-drawdown, missing-price, risk-off/bear/crash, futures blocking opening longs, volume-not-confirmed, trend-not-confirmed, stock-not-green-enough, or weak-relative-edge blockers.

## Earlier Critical Context

- Risk-on starter participation valve v2 was added July 7, 2026.
  - Version: `risk-on-starter-participation-valve-2026-07-07-v2-opening-warmup`.
  - It added `opening_warmup_active` to allowed starter blocker tokens and preserved one-starter-per-day/cycle safety.
- Early paper ML Phase 3A gate was added July 2, 2026.
  - Version: `ml-phase3a-early-paper-gate-2026-07-02-v1`.
  - Live authority remained off.
  - Strict benchmark remains 150 execution rows and 100 observed outcomes before stronger authority.
- Dynamic universe startup timeout fix was added July 1, 2026.
  - Version: `dynamic-universe-builder-2026-07-01-v4-source-symbol-hygiene`.
  - Fixed invalid token leakage and deferred yfinance-heavy startup work.
- Blocked reason cleanup v3 remains live.
  - Versions: `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` and `blocked-entry-reason-selfcheck-overlay-2026-06-30-v3-placeholder-cleanup`.
- Controlled redeployment starter sleeve latest known version remains `controlled-redeployment-starter-sleeve-2026-06-30-v2-borderline-quality-review`.

## Operating Guidance

Routine post-push validation:

1. Use `/paper/self-check` after normal pushes.
2. Optionally use `/paper/risk-on-starter-participation-status` for valve-specific validation.
3. Confirm `overall`, `status`, `failed_required`, `warnings`, `operator_summary`, and changed module version strings.
4. Do not run mutating endpoints unless intentionally repairing or executing a known paper-trade operation.
5. Keep live ML authority off until the strict benchmark and deeper walk-forward/MAE-MFE validation justify stronger authority.

Current next best action:

No immediate health/risk repair is required. Do not loosen v3 further from the current evidence. The v3 telemetry fields are present in `/paper/self-check`, but no valve evaluation has persisted yet. The next useful code change should instrument candidate routing before `core_entry_pipeline._participation_valve_ok` so the operator can see whether candidates are filtered by post-harvest, scanner, rank, or another upstream gate before the risk-on starter valve can evaluate them. The next separate diagnostic cleanup remains TEM post-harvest reason persistence.
