# Automated Trading Project Handoff — Updated July 2, 2026

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
- Routine test link: https://trading-bot-clean.up.railway.app/paper/self-check
- Do not use heavy diagnostic routes unless intentionally debugging.
- Do not run repair routes unless a specific state issue appears.
- Do not run execution routes after hours.
- Do not run mutating Railway endpoints during routine post-push checks.

Latest known good routine self-check supplied by operator on July 2, 2026 at 11:06:34 CDT showed:

- Overall: pass.
- Status: ok.
- Failed required: none.
- Warnings: none.
- Elapsed time: 85.04 ms.
- Checked internal paths: /health and /paper/status.
- Persistent storage configured: true.
- State file: /data/state.json.
- State size: 15,007,905 bytes.
- Trades count: 87.
- Execution rows: 87 / 150.
- Cash: 11100.98.
- Equity: 11100.98.
- Open positions: 0.
- Realized today: +15.44.
- Realized total: +1101.00.
- Unrealized PnL: 0.0.
- Wins today: 1.
- Wins total: 39.
- Losses today: 0.
- Losses total: 15.
- Daily loss pct: 0.053.
- Intraday drawdown pct: 0.053.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.
- Scanner signals found: 58.
- Blocked entries: 15.
- ML rows: 6000.
- ML labeled rows: 1825.
- ML observed outcomes: 54.
- ML predictions: 25.
- Strict Phase 3A ready: false.

## Latest Update — July 2, 2026: Early Paper ML Phase 3A Gate

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

Route added:

- `/paper/ml3a-early-paper-status`

Expected behavior after Railway redeploy:

- `/paper/self-check` should remain fast and should pass.
- `/paper/ml3a-early-paper-status` should show `phase3a_paper_early_ready: true` if the current state remains near the July 2 morning counts: 87 execution rows, 54 observed outcomes, 1825 labeled rows, 25 predictions, and clean risk.
- Decision audit should stop making the 150-row gate the highest priority if early paper gates are passing.
- Chief Advisory Coach should shift to guarded paper Phase 3A advisory mode while still stating that live authority remains off.
- ML strict readiness should still remain separate from early paper readiness.

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

Post-redeploy check:

Routine check:

https://trading-bot-clean.up.railway.app/paper/self-check

Expected:

- `overall: pass`
- `failed_required: []`
- no timeout
- decision audit should no longer frame 150 rows as the only possible Phase 3A transition if early paper gates are passing

Optional direct check:

https://trading-bot-clean.up.railway.app/paper/ml3a-early-paper-status

Expected if current state is still similar to the July 2 morning test:

- `status: ok`
- `phase3a_paper_early_ready: true`
- `strict_phase3a_ready: false`
- `phase3a_live_authority_allowed: false`
- `ml_authority: paper_phase3a_guarded_advisory`
- `does_not_place_trades: true`
- `does_not_bypass_risk_controls: true`

## Latest Verification — July 2, 2026 Morning Self-Check

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

- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` remains live.
- `blocked_entries_count`: 15.
- `signals_found`: 58.
- `visible_blocked_rows_count`: 44.
- `actionable_reason_coverage_pct`: 97.73.
- `rows_with_actionable_reason`: 43.
- `rows_missing_reason_detail`: 1.
- Remaining missing row is still TEM from `state.post_harvest_redeployment.top_candidates_reviewed` with `reason_not_available_in_state_snapshot`.
- Top blocker category: `extension_chase` with 30 rows.
- Other categories: `quality_score` 13 rows and `reason_detail_missing` 1 row.
- Top reasons: `extended_below_5m_ma20`, `score_below_post_harvest_floor`, `entry_score_below_minimum` with extended-starter rank/leader blocks, one futures-bias opening-long block, and the one TEM missing reason.

Top blocked symbols during this check:

- CDE
- NEM
- PHYS
- GLD
- IAU
- RGLD
- AG
- HL
- AMZN
- GDXJ

Top blocked buckets during this check:

- `precious_metals`: 13.
- `semi_leaders`: 9.
- `data_center_infra`: 8.
- `bitcoin_ai_compute`: 6.
- `small_cap_momentum`: 4.
- `cloud_cyber_software`: 3.
- `mega_cap_ai`: 1.

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

Operational interpretation:

- No repair was required.
- The July 1 timeout fix remained validated by the very fast 85 ms self-check.
- The bot was flat in cash after realizing profit and had no active self-defense condition.
- Scanner activity was healthy; 58 signals were seen.
- The current no-entry behavior was selective/risk-controlled, not broken.
- Most visible blocks were extension/chase and quality-score controls, especially in precious metals and related momentum areas.
- Do not loosen thresholds blindly.
- Strict Phase 3A was still not ready under the old 150/100 benchmark, which motivated the early paper-3A gate above.

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

After Railway redeploys the early paper ML Phase 3A gate, use only `/paper/self-check` for routine validation. Optional direct check: `/paper/ml3a-early-paper-status`. If the current counts are similar to the July 2 morning state, the early paper gate should pass while live authority remains off. The next non-urgent cleanup after that remains TEM post-harvest reason persistence.
