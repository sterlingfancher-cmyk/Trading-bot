# Automated Trading Project Handoff — Updated July 1, 2026

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

Latest routine self-check supplied by operator on July 1, 2026 at 12:18:36 CDT showed:

- Overall: pass.
- Status: ok.
- Failed required: none.
- Warnings: none.
- Checked internal paths: /health and /paper/status.
- Persistent storage configured: true.
- State file: /data/state.json.
- State size: 15,156,068 bytes.
- Trades count: 88.
- Execution rows: 88 / 150.
- Cash: 11082.67.
- Equity: 11082.67.
- Open positions: 0.
- Realized today: +36.71.
- Realized total: +1082.67.
- Unrealized PnL: 0.0.
- Wins today: 1.
- Wins total: 40.
- Losses today: 0.
- Losses total: 15.
- Daily loss pct: 0.285.
- Intraday drawdown pct: 0.285.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.
- Scanner signals found: 52.
- Blocked entries: 15.
- ML rows: 6000.
- ML labeled rows: 1842.
- ML observed outcomes: 55.
- ML predictions: 25.
- Phase 3A ready: false.
- ML remains shadow-only.

## Latest Update — July 1, 2026: Symbol Hygiene Guard

### Railway log issue observed

Operator pasted Railway deploy/startup logs from July 1, 2026 around 12:20 PM CDT.

Container health interpretation:

- Container started successfully.
- Gunicorn started successfully.
- Worker booted successfully.
- Logs did not show an app crash.

Problem observed:

- yfinance was trying to download invalid/non-ticker tokens from scanner/dynamic-universe inputs.
- Examples from logs:
  - `LONG`
  - `SHORT`
  - `AUTO`
  - `BEARISH`
  - `CLEAR`
  - `2026-06-04`
  - `CIFRW`
  - `SATS`
- The likely source was dynamic-universe/state symbol flattening: short strings from state rows/log labels/action labels could be treated as symbols.

### Code pushed

Files changed:

- `symbol_hygiene_guard.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

New module version:

- `symbol-hygiene-guard-2026-07-01-v1-invalid-token-filter`

New usercustomize version:

- `usercustomize-symbol-hygiene-guard-2026-07-01-v19`

Commits:

- `ca2d486a183f8ac939e31e7ce8d21a9601ff6fa5`
  - Added `symbol_hygiene_guard.py`.
  - Filters invalid state/log/action tokens before scanner/yfinance usage.
  - Patches core `download_prices`, `fetch_intraday`, and `latest_price` wrappers.
  - Patches `dynamic_universe_builder._symbol`, `_unique`, and `_download_daily` so dynamic seed lists are cleaned before yfinance batch download.
  - Removes likely no-data instruments `CIFRW` and `SATS` by default.
- `030af76995638301984a83cac8dcc16a5875e75e`
  - Wired `symbol_hygiene_guard` into `usercustomize.py` startup before `dynamic_universe_builder`.
  - Added `/paper/symbol-hygiene-guard-status` to optional self-check metadata.
  - Added watchdog re-registration for `symbol_hygiene_guard`.

Route added:

- `/paper/symbol-hygiene-guard-status`

Expected behavior after Railway redeploy:

- The app should still boot normally.
- `/paper/self-check` should remain `overall: pass` with `failed_required: []`.
- `/paper/symbol-hygiene-guard-status` should return `status: ok`, `overall: pass`.
- Future Railway logs should stop showing yfinance attempts for obvious non-tickers like `LONG`, `SHORT`, `AUTO`, `BEARISH`, `CLEAR`, and `2026-06-04`.
- Some true tickers with provider/no-data issues may still occasionally show warnings if Yahoo has transient data gaps, but invalid state/action labels should no longer be sent.

Safety / authority impact:

- Runtime hygiene only.
- Does not place trades.
- Does not lower thresholds.
- Does not bypass risk controls.
- Does not change live authority.
- Does not change ML authority.
- Live trade authority remains none.
- ML authority remains shadow-only.

Post-redeploy check:

Open:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional direct module status:

https://trading-bot-clean.up.railway.app/paper/symbol-hygiene-guard-status

Expected:

- `overall: pass`
- `failed_required: []`
- `symbol-hygiene-guard-2026-07-01-v1-invalid-token-filter` visible on the module route
- no mutating endpoint required

## Latest Verification — July 1, 2026 Afternoon Test

The operator supplied a post-redeploy afternoon `/paper/self-check` payload at 2026-07-01 12:18:36 CDT.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` is live.
- `blocked_entry_top_symbol_details` is present.
- `blocked_entry_missing_reason_rows_sample` is present.
- `blocked_entry_symbol_reason_rollup` is present.
- `blocked_entry_reason_coverage_pct`: 97.73.
- `blocked_entry_rows_missing_reason_detail`: 1.
- Previous v2 reason-detail coverage was 79.63% with 11 missing rows; v3 cleanup improved this to 97.73% with 1 missing row.

Blocked reason audit interpretation:

- The false symbol-only placeholder problem is effectively cleaned up.
- The remaining missing reason row is TEM from `state.post_harvest_redeployment.top_candidates_reviewed` with `reason_not_available_in_state_snapshot`.
- Top blocker category is now `quality_score` with 24 rows.
- Second blocker category is `extension_chase` with 18 rows.
- Other categories: `missing_or_stale_price` 1 row and `reason_detail_missing` 1 row.
- Top reasons include `score_below_post_harvest_floor`, `entry_score_below_minimum`, `extended_starter_rank_too_low`, `extended_starter_not_upper_extension_leader`, dynamic discovery trend/volume confirmation blocks, and one futures bias long block.

Top blocked symbols during the afternoon test:

- DELL
- SMCI
- NTNX
- WULF
- RIOT
- ASTS
- IREN
- APLD
- GSAT
- HUT

Operational interpretation:

- The bot is healthy and flat with 100% cash, no open positions, no self-defense, and clean required checks.
- It is seeing scanner activity but is staying selective because candidates are mostly failing quality score, extension/chase, rank, trend, or volume confirmation gates.
- Do not loosen thresholds blindly.
- If improving anything next after symbol hygiene, persist the full reason for the remaining TEM post-harvest top candidate row so `reason_not_available_in_state_snapshot` goes to zero.

## Latest Code Update — June 30, 2026: Blocked Reason Cleanup / Handoff Rule

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

If `/paper/controlled-redeployment-starter-sleeve-status` returns 404 or `patched: false`, explicitly wire `controlled_redeployment_starter_sleeve` into `wsgi.py` auxiliary registration instead of relying only on `usercustomize.py` auto-registration/watchdog.

## Recent Critical Fixes

### Post-harvest redeployment opportunity governor

Current version:

`post-harvest-opportunity-governor-2026-06-16-v3-cash-gate-throttle`

Route:

- `/paper/post-harvest-opportunity-governor-status`

Purpose:

- Converts prior blunt `losses_today_not_clean` behavior into a graduated opportunity throttle.
- Converts the old fixed 60% post-harvest cash threshold into a graduated soft gate.
- Keeps risk halt, self-defense, hard drawdown, market risk-off, max-position, missing-data, cooldown, and quality gates intact.

Throttle bands:

- Under 0.50% drawdown: normal_opportunity, 1.00 size factor, 50% cash floor.
- 0.50% to 1.00% drawdown: cautious_opportunity, 0.75 size factor, 55% cash floor.
- 1.00% to 2.00% drawdown: defensive_opportunity, 0.50 size factor, 60% cash floor.
- 2.00% to 2.75% drawdown: near_limit_opportunity, 0.35 size factor, 65% cash floor.
- 2.75%+ drawdown: hard_block.

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

After Railway redeploys the symbol hygiene guard update, open `/paper/self-check`. If it passes, optionally open `/paper/symbol-hygiene-guard-status`. The next non-urgent cleanup after that is to persist the exact blocker reason for the remaining TEM post-harvest `top_candidates_reviewed` row so `reason_not_available_in_state_snapshot` goes to zero.
