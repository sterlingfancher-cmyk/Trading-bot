# Automated Trading Project Handoff — Updated July 9, 2026

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
- Early paper Phase 3A guarded-advisory mode: active and confirmed in the July 9 morning self-check.
- Risk-on starter participation valve: v2 is deployed and patched. Direct route confirmed `patched: true` on July 9 at 11:18:31 CDT.
- Risk-on starter valve policy is intentionally narrow: max one starter per day / one per cycle, allocation factor 0.18, high-cash requirement, clean-risk requirement, preferred leadership buckets/symbols only, and no hard safety bypass.
- Strict Phase 3A / stronger authority benchmark: still 150 execution rows and 100 observed outcomes.
- Routine test link: https://trading-bot-clean.up.railway.app/paper/self-check
- Optional risk-on starter valve route: https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status
- Do not use heavy diagnostic routes unless intentionally debugging.
- Do not run repair routes unless a specific state issue appears.
- Do not run execution routes after hours.
- Do not run mutating Railway endpoints during routine post-push checks.

Latest known good routine self-check supplied by operator on July 9, 2026 at 11:13:43 CDT showed:

- Overall: pass.
- Status: ok.
- Failed required: none.
- Warnings: none.
- Elapsed time: 160.65 ms.
- Checked internal paths: /health and /paper/status.
- Persistent storage configured: true.
- State file: /data/state.json.
- State size: 15,057,436 bytes.
- Trades count: 88.
- Execution rows: 88 / 150.
- Cash: 10973.58.
- Equity: 10973.58.
- Open positions: 0.
- Realized today: 0.0.
- Realized total: +973.58.
- Unrealized PnL: 0.0.
- Wins today: 0.
- Wins total: 36.
- Losses today: 0.
- Losses total: 19.
- Daily loss pct: 0.0.
- Intraday drawdown pct: 0.0.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.
- Scanner signals found: 21.
- Scanner-audit blocked entries: 120.
- Decision-audit blocked entries: 10.
- ML rows: 6000.
- ML labeled rows: 1903.
- ML observed outcomes: 55.
- ML predictions: 25.
- Early paper Phase 3A ready: true.
- Live ML authority: false / none.

## Latest Verification — July 9, 2026 Risk-On Starter Valve Direct Status

The operator supplied `/paper/risk-on-starter-participation-status` at 2026-07-09 11:18:31 CDT.

Validation result:

- `status: ok`.
- `overall: pass`.
- `enabled: true`.
- `patched: true`.
- `version: risk-on-starter-participation-valve-2026-07-07-v2-opening-warmup`.
- `latest: {}`.

Policy confirmed by direct route:

- `paper_only: true`.
- `live_trade_authority: none`.
- `authority_changed: false`.
- `does_not_place_trades_directly: true`.
- `does_not_wrap_main_entry_loop: true`.
- `does_not_bypass_cooldowns: true`.
- `does_not_bypass_risk_halts: true`.
- `does_not_bypass_self_defense: true`.
- `does_not_change_live_authority: true`.
- `does_not_change_ml_authority: true`.
- `max_entries_per_day: 1`.
- `max_entries_per_cycle: 1`.
- `max_open_positions: 2`.
- `max_reviewed_rank: 8`.
- `min_cash_pct: 85.0`.
- `min_raw_score: 0.008`.
- `min_rank_score: 0.012`.
- `min_risk_score: 62.0`.
- `alloc_factor: 0.18`.
- Allowed modes: `constructive`, `risk_on`.
- Preferred buckets: `ai_cloud_breakout`, `bitcoin_ai_compute`, `cloud_cyber_software`, `data_center_infra`, `mega_cap_ai`, `memory_storage`, `power_grid_data_center`, `semi_leaders`, `small_cap_momentum`, `space_stocks`.
- Allowed block tokens include `opening_warmup_active`, `early_entry_requires_fvg_reclaim_vwap_ema_confirmation`, `extended_above_5m_ma20`, `extension_chase`, `entry_score_below_minimum`, `score_below_post_harvest_floor`, and extended-starter rank/raw/rank-score blocks.
- Hard block tokens include `self_defense`, `risk_halted`, `halted`, `daily_loss`, `intraday_drawdown`, `cooldown`, `already_held`, `daily_limit`, `cycle_limit`, `missing_price`, `no_price`, `market_regime_block`, `bear`, `crash`, `risk_off`, futures blocking opening longs, `volume_not_confirmed`, `trend_not_confirmed`, `stock_not_green_enough`, and `relative_edge_too_small`.

Interpretation:

- The v2 module is installed and patched correctly.
- The v2 policy includes the exact FVG/opening-warmup blockers it was intended to allow.
- Because `latest` is empty, the valve has not recorded a recent participation-valve evaluation in this process snapshot.
- That means the missed July 9 FVG/reclaim participation cannot be blamed on v2 being absent or unpatched.
- The more likely remaining causes are: candidate flow did not reach `core_entry_pipeline._participation_valve_ok`, the relevant candidates were filtered earlier, the direct route was hit before any post-redeploy candidate evaluation, the candidate was outside preferred bucket/symbol rules, the rank/score/cash/risk requirements failed, or the one-entry cap logic stopped the evaluation.
- Next code work should be telemetry, not risk loosening: persist `risk_on_starter_last_evaluation`, `risk_on_starter_last_block_reason`, and candidate-level evaluation rows into state/operator summary so `/paper/self-check` can explain whether the valve was invoked and why it allowed or blocked.

## Latest Verification — July 9, 2026 Morning Self-Check

The operator supplied a successful morning `/paper/self-check` payload at 2026-07-09 11:13:43 CDT.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `summary_counts`: pass 2, fail 0, warn 0, linked_only 3.
- `/paper/self-check` returned quickly with `elapsed_ms: 160.65`.
- Checked paths were `/health` and `/paper/status` using direct state snapshots.
- `one-test-policy-2026-06-03-decision-audit-summary` remains active.
- Mobile-safe mode remains active.

Early paper Phase 3A status:

- Early paper Phase 3A guarded-advisory mode remains active.
- Decision audit still says: run early paper Phase 3A guarded-advisory mode; do not grant live authority.
- Trade Quality Coach: `execution_rows=88/150`; early paper Phase 3A gate is open with live authority off; continue collecting rows for the strict benchmark.
- ML counts: rows 6000, labeled 1903, observed outcomes 55, predictions 25.
- `phase3a_ready`: true.
- `advisory_only`: true.
- `authority_changed`: false.
- Live authority remains off.

Portfolio / risk status:

- Equity: 10973.58.
- Cash: 10973.58.
- Open positions: 0.
- Realized today: 0.0.
- Realized total: +973.58.
- Unrealized PnL: 0.0.
- Wins today: 0.
- Losses today: 0.
- Daily loss pct: 0.0.
- Intraday drawdown pct: 0.0.
- Self-defense active: false.
- Self-defense reason: feedback loop clear.

Blocked-entry diagnostic status:

- `blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup` remains live.
- `blocked_entries_count`: 120 in scanner audit / 10 in decision audit.
- `signals_found`: 21.
- `visible_blocked_rows_count`: 77.
- `actionable_reason_coverage_pct`: 94.81.
- `rows_with_actionable_reason`: 73.
- `rows_missing_reason_detail`: 4.
- Missing detail symbols now include RGLD, AEM, and BKSY from `scanner_audit.top_blocked_symbols`, plus the persistent TEM post-harvest row.
- Top blocker category: `other_or_unclassified` with 45 rows.
- Other categories: `extension_chase` 15 rows, `quality_score` 13 rows, and `reason_detail_missing` 4 rows.
- Top reasons included `early_entry_requires_fvg_reclaim_vwap_ema_confirmation` 45 rows, `extended_above_5m_ma20` 14 rows, `score_below_post_harvest_floor` 12 rows, three `top_blocked_symbol_reason_not_in_mobile_snapshot` rows, one `extended_below_5m_ma20`, one futures-bias opening-long block, and the persistent TEM missing-reason row.

Top visible blocked symbols during this check:

- RGLD
- FNV
- NEM
- AEM
- PHYS
- IAU
- GLD
- IRDM
- SHOP
- BKSY

Watched momentum symbols:

- Blocked: AMD, AVGO, BKSY, CLSK, CORZ, HUT, MARA, MU, NBIS, PL, RDW, RKLB, SATL, SPIR, WULF.
- Seen: AMD, AVGO, BKSY, CLSK, CORZ, DELL, HIVE, HPE, HUT, LRCX, LUNR, MARA, MU, NBIS, NVTS, PL, RDW, RIOT, RKLB, SATL, SPCX, SPIR, STX, WDC, WULF.

Operational interpretation:

- No repair is required for health/risk.
- The system is healthy, fast, and passing routine checks.
- The bot is flat in cash and self-defense is inactive.
- This snapshot shows the missed-participation pattern that v2 was meant to address: 45 visible rows blocked by `early_entry_requires_fvg_reclaim_vwap_ema_confirmation`, with additional extension and score-floor blocks.
- The direct valve route confirms v2 is patched and has the right allowed tokens, but `latest: {}` means the valve has not captured a recent evaluation.
- Do not loosen v2 further until there is candidate-level valve telemetry showing the actual reject reason.
- The July 9 top blockers were weighted toward precious metals and a few momentum/software/space names, so some candidates may have been outside the preferred bucket/symbol policy.
- The blocked-reason audit regressed from one missing row to four missing rows due to three top-blocked-symbol placeholders. This is diagnostic/reporting debt, not a trading-authority issue.
- Next non-urgent cleanup remains blocker reason persistence: persist full blocker rows for top blocked symbols and the TEM post-harvest row so `top_blocked_symbol_reason_not_in_mobile_snapshot` and `reason_not_available_in_state_snapshot` go to zero.

## Prior Verification — July 8, 2026 Morning Self-Check

The operator supplied a successful morning `/paper/self-check` payload at 2026-07-08 11:48:58 CDT after the July 7 risk-on starter valve v2 patch.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `/paper/self-check` returned very quickly with `elapsed_ms: 80.62`.
- Early paper Phase 3A remained active.
- Live authority remained off.
- Equity and cash were 10973.83.
- Open positions were 0.
- Realized today was -25.01.
- Daily and intraday drawdown were 0.0.
- Self-defense was inactive.
- The visible blockers included `market_risk_not_ok`, `trend_not_confirmed`, and `volume_not_confirmed`, so no further valve loosening was recommended from that snapshot.

## Latest Code Update — July 7, 2026: Risk-On Starter Participation Valve v2

### Reasoning

The July 7 afternoon self-check remained healthy but showed no starter entries and heavy blocking. The top blockers were `early_entry_requires_fvg_reclaim_vwap_ema_confirmation`, `opening_warmup_active`, extension blocks, and score-floor blocks. The initial v1 valve allowed FVG/extension/near-score-floor blocks but did not explicitly allow `opening_warmup_active`, so it could still miss the exact early broad-risk-on participation problem.

### Files changed

- `risk_on_starter_participation_valve.py`
- `PROJECT_HANDOFF.md`

### Module version

- `risk-on-starter-participation-valve-2026-07-07-v2-opening-warmup`

### Commits

- `bae5ff3582f571adde8ea8cd7bb7a45ff8cf97e1`
  - Updated `risk_on_starter_participation_valve.py` to v2.
  - Adds `opening_warmup_active` to the default allowed blocker tokens.
  - Adds SNOW, DUOL, and PLTR to preferred symbols after they appeared as high-score blocked leaders in the July 7 test.
  - Keeps one starter per day / one per cycle.
  - Keeps allocation factor `0.18`.
  - Keeps paper-only behavior.
  - Keeps live authority off.
  - Keeps self-defense, risk halt, cooldown, daily-loss, intraday-drawdown, missing-price, risk-off/bear/crash, volume-not-confirmed, trend-not_confirmed, stock-not-green-enough, and weak-relative-edge blockers intact.
  - Removes prior-valve `market_mode_not_allowed` text from the default hard-block list so the module can use its own risk-on context check instead of being blocked by stale or narrower upstream market-mode text.
- `07a28ed47504a2f0294b805de9351700155f8b7a`
  - Updated handoff with July 7 afternoon self-check and v2 patch notes.
- `98fe492e47e67aca8972ae91cc38f9da289c4502`
  - Updated handoff with July 8 morning self-check interpretation.
- `49d813b770c2d0cd3365df282a101af60c62743a`
  - Updated handoff with July 9 morning self-check interpretation.

### Route

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

## Prior Code Update — July 6, 2026: Risk-On Starter Participation Valve v1

Files changed:

- `risk_on_starter_participation_valve.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

Versions:

- `risk-on-starter-participation-valve-2026-07-06-v1`
- `usercustomize-risk-on-starter-valve-2026-07-06-v21`

Commits:

- `fe6c32a9808601cbd32a024f1af6ad3d7bea864b`
- `fa6bc76bb6962c99d5837dd397f0a43ab74809f4`
- `ac41ea5410e603a541db1723588398725d426361`

Route added:

- `/paper/risk-on-starter-participation-status`

## Prior Verification — July 6, 2026 Morning Self-Check

The operator supplied a successful morning `/paper/self-check` payload at 2026-07-06 11:40:07 CDT, before the risk-on starter valve was added.

Validation result:

- `overall: pass`.
- `status: ok`.
- `failed_required: []`.
- `warnings: []`.
- `/paper/self-check` returned quickly with `elapsed_ms: 224.91`.
- Early paper Phase 3A remained active and correctly guarded.
- Live authority was still off.
- The bot was flat in cash and self-defense was inactive.
- The major visible block pattern was protective extension/FVG-confirmation logic.

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
- Live authority remained off.

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
3. For risk-on starter valve diagnostics, use `/paper/risk-on-starter-participation-status`; current route confirms v2 is patched but `latest` is empty.
4. Do not run mutating endpoints unless specifically repairing or executing a known paper-trade operation.
5. Update this handoff after the code/config change and after interpreting the latest check.

Current next best action:

No immediate repair is required for health/risk. Do not loosen v2 further from the current evidence. The direct valve route confirms the v2 policy is patched, but `latest: {}` means it has not recorded a recent candidate evaluation. The next useful code change should be diagnostic telemetry, not risk loosening: persist risk-on-starter candidate evaluations into state/self-check so the operator can see whether the valve was reached and whether the reject came from market context, preferred bucket/symbol, rank/score, cash/risk, or entry cap. Also persist full blocker rows for top blocked symbols and the TEM post-harvest row so missing-reason coverage returns near 100%.
