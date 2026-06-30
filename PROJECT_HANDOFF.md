# Automated Trading Project Handoff — Updated June 30, 2026

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
- ML authority: shadow-only.
- Routine test link: https://trading-bot-clean.up.railway.app/paper/self-check
- Do not use heavy diagnostic routes unless intentionally debugging.
- Do not run repair routes unless a specific state issue appears.
- Do not run execution routes after hours.
- Do not run mutating Railway endpoints during routine post-push checks.

Latest routine self-check supplied by operator on June 30, 2026 at roughly 12:15 CDT showed:

- Overall: pass.
- Status: ok.
- Failed required: none.
- Warnings: none.
- Checked internal paths: /health and /paper/status.
- Persistent storage configured: true.
- State file: /data/state.json.
- State size: about 15.24 MB.
- Trades count: 87.
- Execution rows: 87 / 150.
- Cash: 10764.61.
- Equity: 11104.71.
- Open positions: 1.
- Position: SNDK.
- SNDK unrealized PnL: +58.76, +20.88%.
- Realized today: +188.28.
- Realized total: +1045.96.
- Wins today: 5.
- Wins total: 39.
- Losses today: 0.
- Losses total: 15.
- Daily loss pct: 0.0.
- Intraday drawdown pct: 0.0.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.
- Scanner signals found: 50.
- Blocked entries: 15.
- ML rows: 6000.
- ML labeled rows: 1915.
- ML observed outcomes: 54.
- ML predictions: 25.
- Phase 3A ready: false.
- ML remains shadow-only.

## Latest Update — June 30, 2026: Blocked Reason Cleanup / Handoff Rule

### Blocked-entry reason audit cleanup

Files changed:

- `blocked_entry_reason_audit.py`
- `blocked_entry_reason_selfcheck_overlay.py`

Current versions after cleanup:

- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup`
- `blocked-entry-reason-selfcheck-overlay-2026-06-30-v3-placeholder-cleanup`

Commits:

- `8a5ac67c37041210b1aff9c310ed4b57e099f1a8`
  - Updated `blocked_entry_reason_audit.py`.
  - Cleans up symbol-only placeholder accounting.
  - Avoids counting `top_blocked_symbol_reason_not_in_mobile_snapshot` as a missing reason when a detailed blocker row already exists for the same symbol.
  - Adds `top_blocked_symbol_details` and `missing_reason_rows_sample`.
- `3c92da5ff94c040f96dbef95556c2fa6eae4db90`
  - Updated `blocked_entry_reason_selfcheck_overlay.py`.
  - Exposes cleaned fields in `/paper/self-check` operator summary/dashboard.

Routes affected:

- `/paper/blocked-entry-reason-audit-status`
- `/paper/blocked-entry-reason-selfcheck-overlay-status`
- `/paper/self-check` via mobile-safe overlay injection

Fields expected in `/paper/self-check` after Railway redeploy:

- `blocked_entry_top_symbol_details`
- `blocked_entry_missing_reason_rows_sample`
- `blocked_entry_symbol_reason_rollup`
- `blocked_entry_reason_coverage_pct`
- `blocked_entry_rows_missing_reason_detail`
- `blocked_entry_missing_reason_symbols`

Safety / authority impact:

- Advisory-only diagnostic cleanup.
- Does not place trades.
- Does not lower thresholds.
- Does not bypass risk controls.
- Does not change live authority.
- Does not change ML authority.
- Live trade authority remains none.
- ML authority remains shadow-only.

Reason for update:

The June 30 self-check showed the audit upgrade was working, but some `top_blocked_symbol_reason_not_in_mobile_snapshot` placeholders were still inflating missing-reason detail counts even when the same symbols had detailed blocker rows elsewhere. The v3 cleanup separates top blocked symbol collection from detailed blocker row extraction and only inserts a missing-reason placeholder when a top blocked symbol truly lacks row-level detail.

Expected post-redeploy check:

Open:

https://trading-bot-clean.up.railway.app/paper/self-check

Expected:

- `overall: pass`
- `failed_required: []`
- audit version `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup`
- overlay version `blocked-entry-reason-selfcheck-overlay-2026-06-30-v3-placeholder-cleanup`
- `blocked_entry_top_symbol_details` present
- `blocked_entry_rows_missing_reason_detail` lower than before unless symbols truly lack detailed rows

### Previous June 30 blocked-reason coverage upgrade

Files changed:

- `blocked_entry_reason_audit.py`
- `blocked_entry_reason_selfcheck_overlay.py`

Versions:

- `blocked-entry-reason-audit-2026-06-30-v2-reason-coverage`
- `blocked-entry-reason-selfcheck-overlay-2026-06-30-v2-reason-coverage`

Commits:

- `9a99c921368826fd54cc8fdf5eef6931a991d13c`
  - Added reason coverage accounting.
  - Fixed `blocked_entries_count` fallback when state had visible rows but count was null.
  - Added nested reason extraction from `quality_info`, `participation_valve`, `score_gate`, `rotation_info`, and related objects.
- `2fa3caf0780cea6ddf656e1c2168fa61b67d7cb7`
  - Exposed reason coverage fields inside `/paper/self-check`.

Operator-confirmed self-check after this v2 update:

- Audit version live: `blocked-entry-reason-audit-2026-06-30-v2-reason-coverage`.
- `blocked_entries_count`: 15.
- `visible_blocked_rows_count`: 54.
- `rows_with_actionable_reason`: 43.
- `rows_missing_reason_detail`: 11.
- `actionable_reason_coverage_pct`: 79.63.
- Top blocker category: `extension_chase` with 28 rows.
- Other blocker categories: `quality_score`, `reason_detail_missing`, `missing_or_stale_price`.
- Top blocked symbols included TEM, DDOG, AMKR, ETN, PLTR, SOUN, ARM, MSFT, BBAI, WPM.

Interpretation:

The bot was seeing opportunities but correctly blocking most of them because they were extended/chasing risk or below quality floors. That is the intended behavior for controlled redeployment; do not loosen risk blindly.

## Controlled Redeployment Starter Sleeve — June 30, 2026

Latest pushed file:

- `controlled_redeployment_starter_sleeve.py`

Latest known version:

- `controlled-redeployment-starter-sleeve-2026-06-30-v2-borderline-quality-review`

Primary route:

- `/paper/controlled-redeployment-starter-sleeve-status`

Purpose:

- Controlled post-harvest redeployment starter sleeve.
- Reviews a limited set of high-ranked candidates after harvest/underdeployment situations.
- Allows only starter-sized redeployment through existing quality gates.
- Sits after post-harvest review and before entry quality finalization.
- Does not wrap the whole app entry function directly.
- Does not bypass cooldowns, self-defense, daily loss, intraday drawdown, risk halt, market-mode, or quality controls.

Policy highlights:

- Paper-only context.
- Max entries per day: 1.
- Max reviewed rank: 5.
- Allocation factor: 0.22.
- Minimum cash percentage: 80%.
- Minimum raw score: 0.0135.
- Minimum rank score: 0.0190.
- Allowed modes: risk_on and constructive.
- Borderline review enabled with score band percentage: 5.0.
- Live trade authority: none.
- ML authority: shadow-only.
- Authority changed: false.

Post-redeploy checks:

- `/paper/controlled-redeployment-starter-sleeve-status`
- `/paper/self-check`

Expected:

- `status: ok`
- `overall: pass`
- version matches `controlled-redeployment-starter-sleeve-2026-06-30-v2-borderline-quality-review`
- `paper_context: true`
- `patched: true`
- authority unchanged

If the route returns 404 or `patched: false`, explicitly wire `controlled_redeployment_starter_sleeve` into `wsgi.py` auxiliary registration instead of relying only on `usercustomize.py` auto-registration/watchdog.

## Recent Critical Fixes

### Post-harvest redeployment opportunity governor

Current version:

`post-harvest-opportunity-governor-2026-06-16-v3-cash-gate-throttle`

Route:

- `/paper/post-harvest-opportunity-governor-status`

Purpose:

- Converts the prior blunt `losses_today_not_clean` behavior into a graduated opportunity throttle.
- Converts the old fixed 60% post-harvest cash threshold into a graduated soft gate.
- Keeps risk halt, self-defense, hard drawdown, market risk-off, max-position, missing-data, cooldown, and quality gates intact.

Runtime patches applied by the governor:

- `post_harvest_redeployment_controller._risk_ok`
- `post_harvest_redeployment_controller._entry_block_safe`
- `post_harvest_redeployment_controller._profit_harvest_ok`
- `post_harvest_redeployment_controller._quality_ok`
- `post_harvest_redeployment_controller._starter_signal`
- `post_harvest_redeployment_controller.select_redeployment_candidates`
- `post_harvest_entry_fallback._risk_ok`

Policy now active:

- `losses_today_policy: throttle_not_hard_block`
- `profit_taking_policy: frees_capital_if_quality_and_risk_are_clean`
- `cash_pct_policy: graduated_soft_gate_not_fixed_hard_block`
- Live trade authority remains none.
- ML authority remains shadow_only.
- Authority changed remains false.

Throttle bands:

- Under 0.50% drawdown: normal_opportunity, 1.00 size factor, 50% cash floor.
- 0.50% to 1.00% drawdown: cautious_opportunity, 0.75 size factor, 55% cash floor.
- 1.00% to 2.00% drawdown: defensive_opportunity, 0.50 size factor, 60% cash floor.
- 2.00% to 2.75% drawdown: near_limit_opportunity, 0.35 size factor, 65% cash floor.
- 2.75%+ drawdown: hard_block.

Commits for the post-harvest update sequence:

- `7a6fb8e018df1368f4c814bb8c9f8b03b9513664`
  - Added `post_harvest_opportunity_governor.py`.
- `cb15363495f33aa1b2133e24caf991e67d5d4e20`
  - Wired `post_harvest_opportunity_governor` into `usercustomize.py` startup.
- `dee509d0f91cd19606ebea5ccd2a0272a329e6ea`
  - Tightened post-harvest opportunity throttle logic.
- `e662d40a5c6483462c0b1f4ff96a4230450b60da`
  - Converted post-harvest cash gate from fixed hard threshold to graduated throttle.

### Space Stock Basket Overlay

File:

- `space_stock_basket.py`

Current version:

- `space-stock-basket-2026-06-16-v1`

Route:

- `/paper/space-stock-basket-status`

Purpose:

Adds a focused space / space-infrastructure theme to the active scanner universe without rewriting `app.py`. This is a metadata and universe overlay only. It does not place trades, change ML authority, bypass risk controls, or force entries.

Symbols added:

- Launch / lunar: RKLB, LUNR, SPCE.
- Satellite connectivity: ASTS, IRDM, GSAT, VSAT, SATS.
- Earth observation / space data: PL, BKSY, SATL, SPIR.
- Space infrastructure: RDW.

Bucket:

- Bucket name: `space_stocks`.
- Default alloc factor: 0.70.
- Default max exposure pct: 0.30.
- Default max positions: 3.
- Environment overrides:
  - `SPACE_STOCKS_ALLOC_FACTOR`
  - `SPACE_STOCKS_MAX_EXPOSURE_PCT`
  - `SPACE_STOCKS_MAX_POSITIONS`

Startup wiring:

- `usercustomize.py` registers `space_stock_basket`.
- `usercustomize.py` watchdog re-registers `space_stock_basket`.
- `/paper/space-stock-basket-status` is included as optional self-check metadata.

Important behavior:

- These stocks are available to the scanner universe.
- They still must pass normal scanner ranking, risk, quality, price, cooldown, sector/bucket exposure, and max-position rules.
- No forced trades.
- No live trading.
- No ML authority change.

Commits for the space basket update:

- `5fea442ff21ce828e7cacca0f22b00f2ec3f17f4`
  - Added `space_stock_basket.py`.
- `73cfd23b4826e69811c32c1244e5d8634400f3b5`
  - Wired `space_stock_basket` into `usercustomize.py` startup and watchdog.

### SPY malformed paper position repair

A prior market surge queue executor entry deducted cash for SPY but stored the position in a malformed format. SPY showed `entry_price` and `qty`, but the normal status route expected legacy fields `entry` and `shares`.

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

Purpose:

Hybrid paper-only market surge deployment mode that prioritizes high-quality individual stock leaders from the scanner while keeping ETFs as a broad-market anchor and fallback.

Routes:

- `/paper/market-surge-deployment-status`
- `/paper/market-surge-deployment-plan`
- `/paper/market-surge-deployment-execute?confirm=1`
- `/paper/market-surge-deployment-auto-fire`
- `/paper/market-surge-deployment-autofire`

Core design:

- Paper-only.
- No live trade authority.
- ML remains shadow-only.
- Requires clean risk controls.
- Requires regular market window.
- Requires high cash percentage.
- Requires surge confirmation.
- Uses scanner-ranked individual stock leaders first during broad market surges.

## Operating Guidance

Routine post-push validation:

1. Use only `/paper/self-check` unless deeper diagnostics are intentionally needed.
2. Confirm `overall`, `status`, `failed_required`, `warnings`, `health`, `status`, `operator_summary`, and any changed module version strings.
3. For route-specific module work, also check that module's status endpoint when required by the change.
4. Do not run mutating endpoints unless specifically repairing or executing a known paper-trade operation.
5. Update this handoff after the code/config change and after interpreting the latest check.

Current next best action:

After Railway redeploy from the latest handoff update and blocked-reason cleanup commits, open:

https://trading-bot-clean.up.railway.app/paper/self-check

Then confirm:

- Overall remains pass.
- No failed required checks.
- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` is live.
- `blocked-entry-reason-selfcheck-overlay-2026-06-30-v3-placeholder-cleanup` is live if surfaced.
- `blocked_entry_top_symbol_details` is present.
- Missing reason detail count is lower unless the symbols truly lack row-level details.
