# Automated Trading Project Handoff — Updated July 6, 2026

## Standing Update Rule

Every future code/configuration update must also update this `PROJECT_HANDOFF.md` file in the same work session. The handoff entry should include:

- Files changed.
- New module/version strings.
- Commit SHA(s).
- Routes affected.
- Authority/safety impact.
- Railway post-redeploy check result or the exact endpoints still needing verification.
- Next recommended action.

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
- Early paper Phase 3A guarded-advisory mode: active and still confirmed in the July 6 morning self-check.
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

## Latest Verification — July 6, 2026 Morning Self-Check

The operator supplied a successful morning `/paper/self-check` payload at 2026-07-06 11:40:07 CDT.

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

Top blocked buckets during this check:

- `semi_leaders`: 17.
- `precious_metals`: 16.
- `cloud_cyber_software`: 7.
- `bitcoin_ai_compute`: 6.
- `small_cap_momentum`: 5.
- `benchmark_etf`: 4.
- `space_stocks`: 4.
- `data_center_infra`: 3.
- `energy_leaders`: 2.
- `mega_cap_ai`: 2.
- `ai_cloud_breakout`: 1.

Watched momentum symbols:

- Blocked: AMD, ASTS, AVGO, BKSY, CLSK, CORZ, HUT, MU, PL, RKLB, SPCE, WULF.
- Seen: AMD, ASTS, AVGO, BKSY, CIFR, CLSK, CORZ, DELL, GEV, HIVE, HPE, HUT, IREN, LRCX, MU, NVTS, PL, RDW, RKLB, SPCE, STX, TER, WDC, WULF.

Operational interpretation:

- No repair is required.
- The system is healthy, fast, and passing routine checks.
- Early paper Phase 3A remains active and correctly guarded; live authority is still off.
- The bot is flat in cash and self-defense is inactive.
- Current no-entry behavior is selective/risk-controlled, not broken.
- The major visible block pattern is protective extension/FVG-confirmation logic, especially in semis, precious metals, cloud/software, bitcoin compute, and space/momentum names.
- Do not loosen thresholds blindly.
- The audit coverage improved to 98.51%, but the same one TEM post-harvest reason row still needs persistence cleanup.
- Next non-urgent cleanup remains TEM post-harvest reason persistence so the final `reason_not_available_in_state_snapshot` row goes to zero.

## Prior Verification — July 2, 2026 Afternoon Early Paper Phase 3A Validation

The operator supplied a successful afternoon `/paper/self-check` payload at 2026-07-02 13:58:36 CDT after the early paper ML Phase 3A gate was deployed.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `summary_counts`: pass 2, fail 0, warn 0, linked_only 3.
- `/paper/self-check` returned quickly with `elapsed_ms: 132.64`.
- Checked paths were `/health` and `/paper/status` using direct state snapshots.
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
- Unrealized PnL: 0.0.
- Wins today: 4.
- Losses today: 2.
- Daily loss pct: 0.421.
- Intraday drawdown pct: 0.421.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.

Operational interpretation:

- No repair was required.
- The early paper Phase 3A gate worked as intended in `/paper/self-check`.
- The system was still paper-only and had not granted live ML authority.
- The bot was flat in cash and self-defense was inactive.
- The day was profitable despite two losses, but realized total dipped from the morning snapshot; keep monitoring trade quality while early paper Phase 3A runs.
- Current no-entry state was selective/risk-controlled, not broken.
- Do not loosen thresholds blindly.

## Latest Code Update — July 2, 2026: Early Paper ML Phase 3A Gate

### Reasoning

The original 150-execution-row gate existed to reduce false confidence, overfitting, regime bias, and noisy feedback-loop learning before allowing stronger ML authority. Because the system is still paper-only and has no live-money authority, it is reasonable to start a guarded paper Phase 3A experiment earlier as long as:

- Live authority remains disabled.
- ML does not bypass risk controls.
- ML does not lower rule thresholds automatically.
- ML does not change sizing authority.
- Existing quality gates, self-defense, cooldowns, and risk controls remain authoritative.
- The stricter 150-row / 100-observed-outcome standard remains the benchmark before stronger or live authority.

### Code pushed

Files changed:

- `ml_phase3a_early_paper_gate.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

New module version:

- `ml-phase3a-early-paper-gate-2026-07-02-v1`

New usercustomize version:

- `usercustomize-ml3a-early-paper-gate-2026-07-02-v20`

Commits:

- `bbd3793118a40052e43e8fd842ffc43efe1a3e61`
  - Added `ml_phase3a_early_paper_gate.py`.
  - Adds a paper-only early Phase 3A gate with default thresholds: 75 execution rows, 50 observed outcomes, 100 labeled rows, 10 predictions, and clean risk.
  - Stores status in `state["ml_phase3a_early_paper_gate"]` and updates `state["ml_phase25"]` with early paper readiness.
  - Adds `/paper/ml3a-early-paper-status`.
  - Patches decision-audit advisory functions so `/paper/self-check` can report early paper-3A readiness instead of treating 150 rows as the only transition point.
  - Does not place trades, does not patch execution functions, does not change sizing, does not lower thresholds, and does not bypass risk controls.
- `378b6f258cdc3b98683ae1d930266133ebb136f4`
  - Wired the early paper Phase 3A gate into `usercustomize.py` startup and watchdog registration.
  - Added `/paper/ml3a-early-paper-status` to optional one-test metadata.
- `fe4bbf5f4d94fef96d5f7716cbce8a8327f35ddf`
  - Updated handoff with early paper Phase 3A rationale, expected checks, and authority guardrails.
- `6a94f207350e5081b2e8b8ee280d88f9e2da96cc`
  - Updated handoff with July 2 afternoon early paper Phase 3A validation.

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

## Prior Verification — July 2, 2026 Morning Self-Check

The operator supplied a successful morning `/paper/self-check` payload at 2026-07-02 11:06:34 CDT.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `summary_counts`: pass 2, fail 0, warn 0, linked_only 3.
- `/paper/self-check` returned quickly with `elapsed_ms: 85.04`.
- Checked paths were `/health` and `/paper/status` using direct state snapshots.
- `one-test-policy-2026-06-03-decision-audit-summary` remains active.
- Mobile-safe mode remains active.

Portfolio / risk status:

- Equity: 11100.98.
- Cash: 11100.98.
- Open positions: 0.
- Realized today: +15.44.
- Realized total: +1101.00.
- Unrealized PnL: 0.0.
- Losses today: 0.
- Daily loss pct: 0.053.
- Intraday drawdown pct: 0.053.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.

Blocked-entry diagnostic status:

- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` remained live.
- `blocked_entries_count`: 15.
- `signals_found`: 58.
- `visible_blocked_rows_count`: 44.
- `actionable_reason_coverage_pct`: 97.73.
- `rows_with_actionable_reason`: 43.
- `rows_missing_reason_detail`: 1.
- Remaining missing row was TEM from `state.post_harvest_redeployment.top_candidates_reviewed` with `reason_not_available_in_state_snapshot`.
- Top blocker category: `extension_chase` with 30 rows.
- Other categories: `quality_score` 13 rows and `reason_detail_missing` 1 row.

Decision-audit status before early paper-3A gate:

- `decision-audit-consolidation-2026-06-04-v6-chief-advisory-coach` was live.
- `post_harvest_outcome`: blocked.
- `post_harvest_reason`: post_harvest_controlled_redeployment_candidates.
- `candidate_symbols`: TEM.
- `entries_count`: 0.
- `open_positions_count`: 0.
- `rejected_signals_count`: 15.
- `self_defense_active`: false.
- ML rows: 6000.
- ML labeled rows: 1825.
- ML observed outcomes: 54.
- ML predictions: 25.
- Strict Phase 3A ready: false.

## Prior Verification — July 1, 2026 Clean Post-Timeout Self-Check

The operator confirmed Railway logs looked clean and supplied a successful `/paper/self-check` payload at 2026-07-01 12:37:28 CDT after the dynamic-universe v4 source patch.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `summary_counts`: pass 2, fail 0, warn 0, linked_only 3.
- `/paper/self-check` returned quickly with `elapsed_ms: 286.92`, confirming the timeout condition was resolved.
- Checked paths were `/health` and `/paper/status` using direct state snapshots.
- Railway logs were reported clean by the operator after redeploy.

Operational interpretation:

- The dynamic-universe startup timeout fix worked.
- The app was healthy, responsive, and passing required checks.
- The bot was active enough to detect 59 signals but remained selective.
- The blocks were mostly quality/profit-guard/cooldown logic, not symbol hygiene failure.

## Latest Code Update — July 1, 2026: Dynamic Universe Startup Timeout Fix

Files changed:

- `dynamic_universe_builder.py`
- `PROJECT_HANDOFF.md`

New dynamic universe version:

- `dynamic-universe-builder-2026-07-01-v4-source-symbol-hygiene`

Commit:

- `3ef1a556351afaf8f7a9cfd1f50f7e0353299f97`
  - Hardened `dynamic_universe_builder.py` at the source.
  - Added reserved-word/date/numeric/no-data symbol filtering directly in `_symbol()` and `_unique()`.
  - Stopped `_flatten_symbols()` from scraping free-floating strings in state, which is where labels like `LONG`, `AUTO`, `BLOCKED`, and dates leaked from.
  - Removed known provider/no-data instruments from default theme baskets: `CIFRW`, `SATS`, `BITF`, `SDIG`, `PSTG`.
  - Changed startup/register/apply behavior to lightweight patch-only mode.
  - Deferred the expensive yfinance-backed universe build until `scan_signals()` actually runs or `/paper/dynamic-universe-builder-status?force=1` is explicitly requested.

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

New module version:

- `symbol-hygiene-guard-2026-07-01-v1-invalid-token-filter`

New usercustomize version at that time:

- `usercustomize-symbol-hygiene-guard-2026-07-01-v19`

Commits:

- `ca2d486a183f8ac939e31e7ce8d21a9601ff6fa5`
- `030af76995638301984a83cac8dcc16a5875e75e`
- `fa0a03bc3c343790ad003e8ef3d78087188a387f`

Route added:

- `/paper/symbol-hygiene-guard-status`

Interpretation:

This wrapper remains useful as an additional runtime safety net, but the stronger fix was the direct v4 source patch to `dynamic_universe_builder.py`.

## Prior Verification — July 1, 2026 Afternoon Test

The operator supplied a post-redeploy afternoon `/paper/self-check` payload at 2026-07-01 12:18:36 CDT.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` was live.
- `blocked_entry_reason_coverage_pct`: 97.73.
- `blocked_entry_rows_missing_reason_detail`: 1.

Operational interpretation:

- The bot was healthy and flat with 100% cash, no open positions, no self-defense, and clean required checks.
- It was seeing scanner activity but staying selective because candidates were mostly failing quality score, extension/chase, rank, trend, or volume confirmation gates.

## Latest Code Update — June 30, 2026: Blocked Reason Cleanup

Files changed:

- `blocked_entry_reason_audit.py`
- `blocked_entry_reason_selfcheck_overlay.py`

Current versions after cleanup:

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
3. For route-specific module work, also check that module's status endpoint when required by the change.
4. Do not run mutating endpoints unless specifically repairing or executing a known paper-trade operation.
5. Update this handoff after the code/config change and after interpreting the latest check.

Current next best action:

No immediate repair is required. Continue using only `/paper/self-check` for routine validation while early paper Phase 3A guarded-advisory mode runs. The July 6 morning state is flat in cash with clean risk and no drawdown. Watch whether the early-entry/FVG confirmation and extension-chase blocks repeatedly prevent strong later winners before loosening anything. Keep live ML authority off until the strict benchmark and deeper walk-forward/MAE-MFE validation justify stronger authority. The next non-urgent cleanup remains TEM post-harvest reason persistence.
