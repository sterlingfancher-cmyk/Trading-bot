# Automated Trading Project Handoff — Updated July 6, 2026

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
- Early paper Phase 3A guarded-advisory mode: active and confirmed in the July 6 morning self-check.
- New risk-on starter participation valve: added July 6, 2026; awaiting Railway redeploy validation.
- Strict Phase 3A / stronger authority benchmark: still 150 execution rows and 100 observed outcomes.
- Routine test link: https://trading-bot-clean.up.railway.app/paper/self-check
- Do not use heavy diagnostic routes unless intentionally debugging.
- Do not run repair routes unless a specific state issue appears.
- Do not run execution routes after hours.
- Do not run mutating Railway endpoints during routine post-push checks.

Latest known good routine self-check supplied by operator on July 6, 2026 at 11:40:07 CDT showed:

- Overall: pass.
- Status: ok.
- Failed required: none.
- Warnings: none.
- Elapsed time: 224.91 ms.
- Checked internal paths: /health and /paper/status.
- Persistent storage configured: true.
- State file: /data/state.json.
- State size: 15,082,217 bytes.
- Trades count: 88.
- Execution rows: 88 / 150.
- Cash: 10969.66.
- Equity: 10969.66.
- Open positions: 0.
- Realized today: 0.0.
- Realized total: +969.68.
- Unrealized PnL: 0.0.
- Wins today: 0.
- Wins total: 38.
- Losses today: 0.
- Losses total: 17.
- Daily loss pct: 0.0.
- Intraday drawdown pct: 0.0.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.
- Scanner signals found: 17.
- Scanner-audit blocked entries: 49.
- Decision-audit blocked entries: 14.
- ML rows: 6000.
- ML labeled rows: 1899.
- ML observed outcomes: 55.
- ML predictions: 25.
- Early paper Phase 3A ready: true.
- Live ML authority: false / none.

## Latest Code Update — July 6, 2026: Risk-On Starter Participation Valve

### Reasoning

The July 6 morning check and operator screenshots showed a broad green morning: S&P 500 was up about 0.68%, QQQ was up about 1.65%, and many individual growth/semiconductor/momentum names appeared green. The bot was healthy and risk-clean but stayed 100% cash while most blockers were extension/FVG confirmation, early-entry reclaim requirements, and near-score-floor starter blocks.

The intended behavior is not to remove those protections. The intended behavior is to add a narrow, paper-only starter exception for broad risk-on mornings so the account can participate with one small starter instead of waiting for a perfect FVG/VWAP/EMA reclaim that may never come on trend-grind days.

### Files changed

- `risk_on_starter_participation_valve.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### New module version

- `risk-on-starter-participation-valve-2026-07-06-v1`

### New usercustomize version

- `usercustomize-risk-on-starter-valve-2026-07-06-v21`

### Commits

- `fe6c32a9808601cbd32a024f1af6ad3d7bea864b`
  - Added `risk_on_starter_participation_valve.py`.
  - Patches only `core_entry_pipeline._participation_valve_ok`.
  - Calls the prior/base participation valve first; only evaluates the new exception if prior valves do not allow the trade.
  - Allows at most one small paper starter per day and one per cycle.
  - Uses allocation factor `0.18`.
  - Requires paper context, high cash, low/no open positions, clean risk, allowed market mode, and risk-on confirmation.
  - Requires the blocker to be an allowed participation-style blocker such as FVG/opening-range reclaim, extension/chase, entry-score floor, or existing extended-starter rank/raw/rank-score blocks.
  - Rejects hard blockers such as self-defense, risk halt, cooldown, daily loss, intraday drawdown, missing price, futures blocking opening longs, risk-off/bear/crash context, volume-not-confirmed, trend-not-confirmed, stock-not-green-enough, and relative-edge-too-small.
  - Does not wrap the main entry loop and does not place trades directly.
- `fa6bc76bb6962c99d5837dd397f0a43ab74809f4`
  - Wired `risk_on_starter_participation_valve` into `usercustomize.py` after `extended_leader_starter_valve` and before `controlled_redeployment_starter_sleeve`.
  - Added `/paper/risk-on-starter-participation-status` to optional one-test metadata.
  - Added watchdog registration for the new module.

### Route added

- `/paper/risk-on-starter-participation-status`

### Safety / authority impact

- Paper-only participation overlay.
- Live trade authority remains none.
- ML live authority remains none.
- Does not bypass self-defense.
- Does not bypass risk halts.
- Does not bypass cooldowns.
- Does not bypass daily-loss or intraday-drawdown controls.
- Does not place trades directly.
- Does not wrap the main entry loop.
- Does not lower the global entry threshold.
- Does not open more than one risk-on starter per day.
- Uses starter allocation only.
- Existing quality/risk/entry pipeline remains authoritative.

### Post-redeploy checks

Routine check:

https://trading-bot-clean.up.railway.app/paper/self-check

Expected:

- `overall: pass`.
- `failed_required: []`.
- `warnings: []`.
- Self-check remains fast.
- Early paper Phase 3A remains active.
- Live authority remains off.

Optional direct check:

https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status

Expected:

- `status: ok`.
- `patched: true`.
- `version: risk-on-starter-participation-valve-2026-07-06-v1`.
- Policy shows max entries per day 1, alloc factor 0.18, paper-only true, live authority none, and no bypass of cooldowns/self-defense/risk halts.

Expected behavior on a broad risk-on morning:

- If SPY/S&P and QQQ-style context is risk-on, the book is mostly cash, risk is clean, and a preferred leadership candidate is blocked only by FVG/extension/near-score-floor logic, the valve may allow one small paper starter.
- It should still block if the candidate lacks trend/volume confirmation, has hard risk blockers, is in cooldown, or if market context is not risk-on.

## Latest Verification — July 6, 2026 Morning Self-Check

The operator supplied a successful morning `/paper/self-check` payload at 2026-07-06 11:40:07 CDT, before the risk-on starter valve was added.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `summary_counts`: pass 2, fail 0, warn 0, linked_only 3.
- `/paper/self-check` returned quickly with `elapsed_ms: 224.91`.
- Checked paths were `/health` and `/paper/status` using direct state snapshots.
- `one-test-policy-2026-06-03-decision-audit-summary` remains active.
- Mobile-safe mode remains active.

Early paper Phase 3A status:

- Early paper Phase 3A guarded-advisory mode remains active.
- Decision audit still says: run early paper Phase 3A guarded-advisory mode; do not grant live authority.
- Trade Quality Coach: `execution_rows=88/150`; early paper Phase 3A gate is open with live authority off; continue collecting rows for the strict benchmark.
- ML counts: rows 6000, labeled 1899, observed outcomes 55, predictions 25.
- `phase3a_ready`: true.
- `advisory_only`: true.
- `authority_changed`: false.
- Live authority remains off.
- Strict 150-row benchmark remains the reference for stronger authority.

Portfolio / risk status:

- Equity: 10969.66.
- Cash: 10969.66.
- Open positions: 0.
- Realized today: 0.0.
- Realized total: +969.68.
- Unrealized PnL: 0.0.
- Wins today: 0.
- Losses today: 0.
- Daily loss pct: 0.0.
- Intraday drawdown pct: 0.0.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.

Blocked-entry diagnostic status:

- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` remains live.
- `blocked_entries_count`: 49 in scanner audit / 14 in decision audit.
- `signals_found`: 17.
- `visible_blocked_rows_count`: 67.
- `actionable_reason_coverage_pct`: 98.51.
- `rows_with_actionable_reason`: 66.
- `rows_missing_reason_detail`: 1.
- Remaining missing row is still TEM from `state.post_harvest_redeployment.top_candidates_reviewed` with `reason_not_available_in_state_snapshot`.
- Top blocker category: `extension_chase` with 29 rows.
- Other categories: `other_or_unclassified` 24 rows, `quality_score` 13 rows, and `reason_detail_missing` 1 row.
- Top reasons included `early_entry_requires_fvg_reclaim_vwap_ema_confirmation`, `extended_above_5m_ma20`, `score_below_post_harvest_floor`, extended-starter rank/raw/rank-score blocks, one futures-bias opening-long block, and the single TEM missing-reason row.

Top blocked symbols during this check:

- GOLD
- AEM
- NVDA
- HL
- GLD
- GDX
- IAU
- PHYS
- WPM
- SILJ

Watched momentum symbols:

- Blocked: AMD, ASTS, AVGO, BKSY, CLSK, CORZ, HUT, MU, PL, RKLB, SPCE, WULF.
- Seen: AMD, ASTS, AVGO, BKSY, CIFR, CLSK, CORZ, DELL, GEV, HIVE, HPE, HUT, IREN, LRCX, MU, NVTS, PL, RDW, RKLB, SPCE, STX, TER, WDC, WULF.

Operational interpretation:

- No repair was required before this change.
- The system was healthy, fast, and passing routine checks.
- Early paper Phase 3A remained active and correctly guarded; live authority was still off.
- The bot was flat in cash and self-defense was inactive.
- The major visible block pattern was protective extension/FVG-confirmation logic.
- The risk-on starter participation valve was added specifically to address this missed-participation pattern without loosening the entire system.

## Prior Verification — July 2, 2026 Afternoon Early Paper Phase 3A Validation

The operator supplied a successful afternoon `/paper/self-check` payload at 2026-07-02 13:58:36 CDT after the early paper ML Phase 3A gate was deployed.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `/paper/self-check` returned quickly with `elapsed_ms: 132.64`.
- Decision audit changed posture as intended.
- `phase3a_ready`: true.
- Chief Advisory Coach next action: run early paper Phase 3A guarded-advisory mode; do not grant live authority.
- Trade Quality Coach next action: `execution_rows=88/150`; early paper Phase 3A gate was open with live authority off; continue collecting rows for the strict benchmark.
- ML counts: rows 6000, labeled 1968, observed outcomes 55, predictions 25.
- `advisory_only`: true.
- `authority_changed`: false.
- Live authority remained off.

Portfolio / risk status:

- Equity: 10969.66.
- Cash: 10969.66.
- Open positions: 0.
- Realized today: +112.00.
- Realized total: +969.68.
- Wins today: 4.
- Losses today: 2.
- Self-defense active: false.

## Latest Code Update — July 2, 2026: Early Paper ML Phase 3A Gate

Files changed:

- `ml_phase3a_early_paper_gate.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

Versions:

- `ml-phase3a-early-paper-gate-2026-07-02-v1`
- `usercustomize-ml3a-early-paper-gate-2026-07-02-v20`

Commits:

- `bbd3793118a40052e43e8fd842ffc43efe1a3e61`
- `378b6f258cdc3b98683ae1d930266133ebb136f4`
- `fe4bbf5f4d94fef96d5f7716cbce8a8327f35ddf`
- `6a94f207350e5081b2e8b8ee280d88f9e2da96cc`

Route added:

- `/paper/ml3a-early-paper-status`

Safety / authority impact:

- Paper advisory only.
- Live trade authority remains none.
- ML live authority remains none.
- Execution authority remains false.
- Risk-control authority remains false.
- Sizing authority remains false.
- Does not place trades.
- Does not lower thresholds.
- Does not bypass risk controls.
- Does not disable self-defense, cooldowns, or quality gates.

## Prior Verification — July 1, 2026 Clean Post-Timeout Self-Check

The operator confirmed Railway logs looked clean and supplied a successful `/paper/self-check` payload at 2026-07-01 12:37:28 CDT after the dynamic-universe v4 source patch.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `/paper/self-check` returned quickly with `elapsed_ms: 286.92`, confirming the timeout condition was resolved.

## Latest Code Update — July 1, 2026: Dynamic Universe Startup Timeout Fix

Files changed:

- `dynamic_universe_builder.py`
- `PROJECT_HANDOFF.md`

Version:

- `dynamic-universe-builder-2026-07-01-v4-source-symbol-hygiene`

Commit:

- `3ef1a556351afaf8f7a9cfd1f50f7e0353299f97`

Safety / authority impact:

- Runtime/source hygiene only.
- Does not place trades.
- Does not lower thresholds.
- Does not bypass risk controls.
- Does not change live authority.
- Does not change ML authority.

## Previous Update — July 1, 2026: Symbol Hygiene Guard

Files changed:

- `symbol_hygiene_guard.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

Version:

- `symbol-hygiene-guard-2026-07-01-v1-invalid-token-filter`

Commits:

- `ca2d486a183f8ac939e31e7ce8d21a9601ff6fa5`
- `030af76995638301984a83cac8dcc16a5875e75e`
- `fa0a03bc3c343790ad003e8ef3d78087188a387f`

Route added:

- `/paper/symbol-hygiene-guard-status`

## Latest Code Update — June 30, 2026: Blocked Reason Cleanup

Files changed:

- `blocked_entry_reason_audit.py`
- `blocked_entry_reason_selfcheck_overlay.py`

Versions:

- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup`
- `blocked-entry-reason-selfcheck-overlay-2026-06-30-v3-placeholder-cleanup`

Commits:

- `8a5ac67c37041210b1aff9c310ed4b57e099f1a8`
- `3c92da5ff94c040f96dbef95556c2fa6eae4db90`

Safety / authority impact:

- Advisory-only diagnostic cleanup.
- Does not place trades.
- Does not lower thresholds.
- Does not bypass risk controls.
- Does not change live authority.
- Does not change ML authority.

## Controlled Redeployment Starter Sleeve — June 30, 2026

Latest known version:

- `controlled-redeployment-starter-sleeve-2026-06-30-v2-borderline-quality-review`

Primary route:

- `/paper/controlled-redeployment-starter-sleeve-status`

Purpose:

- Controlled post-harvest redeployment starter sleeve.
- Reviews a limited set of high-ranked candidates after harvest/underdeployment situations.
- Allows only starter-sized redeployment through existing quality gates.
- Does not bypass cooldowns, self-defense, daily loss, intraday drawdown, risk halt, market-mode, or quality controls.

## Recent Critical Fixes

### Post-harvest redeployment opportunity governor

Current version:

`post-harvest-opportunity-governor-2026-06-16-v3-cash-gate-throttle`

Route:

- `/paper/post-harvest-opportunity-governor-status`

### Space Stock Basket Overlay

File:

- `space_stock_basket.py`

Current version:

- `space-stock-basket-2026-06-16-v1`

Route:

- `/paper/space-stock-basket-status`

### SPY malformed paper position repair

Fixed with:

- `surge_state_repair.py`
- Version: `surge-state-repair-2026-06-08-v4-clear-stale-halt-flag`

Do not run the repair endpoint again unless the state becomes malformed again.

Repair routes:

- `/paper/surge-state-repair-status`
- `/paper/surge-state-repair?confirm=1`

### Market Surge Deployment Mode

File:

- `market_surge_deployment_mode.py`

Current known version from June 16 handoff:

- `market-surge-deployment-mode-2026-06-16-v3-hybrid-stock-leaders`

Routes:

- `/paper/market-surge-deployment-status`
- `/paper/market-surge-deployment-plan`
- `/paper/market-surge-deployment-execute?confirm=1`
- `/paper/market-surge-deployment-auto-fire`
- `/paper/market-surge-deployment-autofire`

## Operating Guidance

Routine post-push validation:

1. Use only `/paper/self-check` unless deeper diagnostics are intentionally needed.
2. Confirm `overall`, `status`, `failed_required`, `warnings`, `health`, `status`, `operator_summary`, and any changed module version strings.
3. For route-specific module work, optionally check `/paper/risk-on-starter-participation-status` after the July 6 valve update.
4. Do not run mutating endpoints unless specifically repairing or executing a known paper-trade operation.
5. Update this handoff after the code/config change and after interpreting the latest check.

Current next best action:

After Railway redeploys, run `/paper/self-check`. Optional direct route: `/paper/risk-on-starter-participation-status`. If the route is patched and the next broad risk-on morning occurs with clean risk and high cash, monitor whether the valve allows one small starter in a preferred leader rather than blocking every FVG/extension candidate. Keep live ML authority off until the strict benchmark and deeper walk-forward/MAE-MFE validation justify stronger authority. The next non-urgent cleanup remains TEM post-harvest reason persistence.
