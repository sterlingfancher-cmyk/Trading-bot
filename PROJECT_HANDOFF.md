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

Latest known good routine self-check supplied by operator on July 1, 2026 at 12:18:36 CDT showed:

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

## Latest Update — July 1, 2026: Dynamic Universe Startup Timeout Fix

### Railway issue observed

Operator pasted Railway logs from July 1, 2026 around 12:27 PM CDT.

Container health interpretation:

- Container started successfully.
- Gunicorn started successfully.
- Worker booted successfully.
- Logs did not show a crash.

Problem observed:

- `/paper/self-check` timed out.
- yfinance batch downloads were still running during startup/registration and still included invalid state/action tokens.
- Examples from logs:
  - `LONG`
  - `AUTO`
  - `EQUITY`
  - `REJECTED`
  - `BLOCKED`
  - `NONE`
  - `COOLDOWN`
  - `CONSTRUCTIVE`
  - `NEUTRAL`
  - `2026-07-01`
  - `CIFRW`
  - `SATS`
  - `BITF`
  - `SDIG`
  - `PSTG`

Root cause:

- The first `symbol_hygiene_guard.py` runtime wrapper was useful but not early enough for all paths.
- `dynamic_universe_builder.py` itself still accepted short alphanumeric state strings as tickers.
- `dynamic_universe_builder.apply()` and route registration called a yfinance-backed universe build during app startup, which could block the worker and make `/paper/self-check` time out.

### Code pushed

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
  - Added `source_hygiene_active` and `recent_rejected_seed_tokens` telemetry.
  - Changed startup/register/apply behavior to lightweight patch-only mode.
  - Deferred the expensive yfinance-backed universe build until `scan_signals()` actually runs or `/paper/dynamic-universe-builder-status?force=1` is explicitly requested.

Expected behavior after Railway redeploy:

- App should boot faster.
- `/paper/self-check` should load instead of timing out.
- Invalid tokens should no longer appear in yfinance 30d batch download logs.
- `/paper/dynamic-universe-builder-status` should be lightweight by default and should not force yfinance.
- Use `/paper/dynamic-universe-builder-status?force=1` only when intentionally testing the heavy yfinance-backed builder.

Safety / authority impact:

- Runtime/source hygiene only.
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

Expected:

- `overall: pass`
- `failed_required: []`
- no timeout
- dynamic universe version should be `dynamic-universe-builder-2026-07-01-v4-source-symbol-hygiene` if surfaced through optional metadata/status route

Optional direct lightweight route:

https://trading-bot-clean.up.railway.app/paper/dynamic-universe-builder-status

Expected:

- `status: ok`
- `overall: pass`
- `startup_heavy_build_deferred: true`
- `source_hygiene_active: true`

Do not use `?force=1` during routine checks unless intentionally running the heavy builder.

## Previous Update — July 1, 2026: Symbol Hygiene Guard

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
- `030af76995638301984a83cac8dcc16a5875e75e`
  - Wired `symbol_hygiene_guard` into `usercustomize.py` startup before `dynamic_universe_builder`.
  - Added `/paper/symbol-hygiene-guard-status` to optional self-check metadata.
  - Added watchdog re-registration for `symbol_hygiene_guard`.
- `fa0a03bc3c343790ad003e8ef3d78087188a387f`
  - Updated handoff with first symbol hygiene pass.

Route added:

- `/paper/symbol-hygiene-guard-status`

Interpretation:

This wrapper remains useful as an additional runtime safety net, but the stronger fix is the direct v4 source patch to `dynamic_universe_builder.py` above.

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

Operational interpretation:

- The bot was healthy and flat with 100% cash, no open positions, no self-defense, and clean required checks.
- It was seeing scanner activity but staying selective because candidates were mostly failing quality score, extension/chase, rank, trend, or volume confirmation gates.
- Do not loosen thresholds blindly.
- If improving anything after startup/symbol hygiene, persist the full reason for the remaining TEM post-harvest top candidate row so `reason_not_available_in_state_snapshot` goes to zero.

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

Safety / authority impact:

- Advisory-only diagnostic cleanup.
- Does not place trades.
- Does not lower thresholds.
- Does not bypass risk controls.
- Does not change live authority.
- Does not change ML authority.
- Live trade authority remains none.
- ML authority remains shadow-only.

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

### Space Stock Basket Overlay

File:

- `space_stock_basket.py`

Current version:

- `space-stock-basket-2026-06-16-v1`

Route:

- `/paper/space-stock-basket-status`

Purpose:

Adds a focused space / space-infrastructure theme to the active scanner universe without rewriting `app.py`. This is a metadata and universe overlay only. It does not place trades, change ML authority, bypass risk controls, or force entries.

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

After Railway redeploys the dynamic universe v4 source patch, open `/paper/self-check`. It should no longer time out because dynamic-universe yfinance work is no longer run at startup or ordinary route registration. Optional check: `/paper/dynamic-universe-builder-status` should be lightweight and show `startup_heavy_build_deferred: true`.
