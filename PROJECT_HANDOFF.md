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
- Risk-on starter participation valve: v3 telemetry update pushed July 9, 2026; awaiting Railway redeploy validation.
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
- Scanner signals found: 21.
- Scanner-audit blocked entries: 120.
- Decision-audit blocked entries: 10.
- ML rows: 6000.
- ML labeled rows: 1903.
- ML observed outcomes: 55.
- ML predictions: 25.
- Early paper Phase 3A ready: true.
- Live ML authority: false / none.

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
  - Direct route now exposes persisted `state_telemetry`, `last_evaluation`, `last_status`, `last_reason`, `recent_evaluations`, `counters`, and `telemetry_persisted`.
  - Does not change entry thresholds, allocation, allowed blockers, hard blockers, live authority, ML authority, or trade execution behavior.
- `7d88a9dcf9c0b56bf2fe05dff07fb91dec22e100`
  - Updated `one_link_check.py` so `/paper/self-check` promotes risk-on starter telemetry into `dashboard["risk_on_starter_participation"]` and `risk_on_starter_participation_summary`.
  - Adds operator summary fields including `risk_on_starter_status`, `risk_on_starter_version`, `risk_on_starter_enabled`, `risk_on_starter_patched`, `risk_on_starter_telemetry_persisted`, `risk_on_starter_last_status`, `risk_on_starter_last_reason`, `risk_on_starter_last_symbol`, `risk_on_starter_last_bucket`, `risk_on_starter_last_score`, `risk_on_starter_last_rank_score`, `risk_on_starter_last_rank_index`, `risk_on_starter_last_prior_reason`, matched/hard-block tokens, counters, and recent evaluations.
  - Adds `/paper/risk-on-starter-participation-status` to one-test metadata as a safe optional governance endpoint.

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

### Post-redeploy checks

Routine check:

https://trading-bot-clean.up.railway.app/paper/self-check

Expected after redeploy:

- `overall: pass`.
- `failed_required: []`.
- Self-check remains fast.
- `one_test_policy_version` should show `one-test-policy-2026-07-09-risk-on-starter-telemetry`.
- Operator summary should include `risk_on_starter_*` fields.
- If no candidate has reached the valve yet, telemetry may show patched/enabled with no recent evaluation. After the next candidate cycle, it should show last evaluation details.

Optional direct check:

https://trading-bot-clean.up.railway.app/paper/risk-on-starter-participation-status

Expected after redeploy:

- `status: ok`.
- `patched: true`.
- Version should show `risk-on-starter-participation-valve-2026-07-09-v3-telemetry`.
- `policy.telemetry_max_rows` should be present.
- `state_telemetry`, `last_evaluation`, `recent_evaluations`, `counters`, and `telemetry_persisted` should appear.

### What this should answer next

After a fresh scanner/entry cycle, the operator should be able to see whether the risk-on starter valve:

- was reached by the candidate;
- passed through because the prior valve allowed;
- blocked because the symbol was outside preferred bucket/symbol policy;
- blocked by rank, score, cash, open-position count, or daily/cycle cap;
- blocked because market context was not risk-on/constructive;
- blocked because the prior reason did not match allowed opening-warmup/FVG/extension/score-floor tokens;
- blocked because a hard blocker was present; or
- allowed one starter.

## Latest Verification — July 9, 2026 Risk-On Starter Valve Direct Status

The operator supplied `/paper/risk-on-starter-participation-status` at 2026-07-09 11:18:31 CDT before v3 telemetry was pushed.

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
- `max_entries_per_day: 1`.
- `max_entries_per_cycle: 1`.
- `min_cash_pct: 85.0`.
- `min_raw_score: 0.008`.
- `min_rank_score: 0.012`.
- `min_risk_score: 62.0`.
- `alloc_factor: 0.18`.
- Allowed modes: `constructive`, `risk_on`.
- Allowed block tokens included `opening_warmup_active`, `early_entry_requires_fvg_reclaim_vwap_ema_confirmation`, `extended_above_5m_ma20`, `extension_chase`, `entry_score_below_minimum`, `score_below_post_harvest_floor`, and extended-starter rank/raw/rank-score blocks.
- Hard block tokens included `self_defense`, `risk_halted`, `halted`, `daily_loss`, `intraday_drawdown`, `cooldown`, `already_held`, `daily_limit`, `cycle_limit`, `missing_price`, `no_price`, `market_regime_block`, `bear`, `crash`, `risk_off`, futures blocking opening longs, `volume_not_confirmed`, `trend_not_confirmed`, `stock_not_green_enough`, and `relative_edge_too_small`.

Interpretation:

- The v2 module was installed and patched correctly.
- The v2 policy included the exact FVG/opening-warmup blockers it was intended to allow.
- Because `latest` was empty, the valve had not recorded a recent participation-valve evaluation in that process snapshot.
- The more likely remaining causes were: candidate flow did not reach `core_entry_pipeline._participation_valve_ok`, relevant candidates were filtered earlier, direct route was hit before a fresh post-redeploy candidate evaluation, candidate was outside preferred bucket/symbol rules, rank/score/cash/risk requirements failed, or the one-entry cap stopped evaluation.

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
- Mobile-safe mode remained active.
- Early paper Phase 3A guarded-advisory mode remained active.
- Live authority remained off.
- Equity: 10973.58.
- Cash: 10973.58.
- Open positions: 0.
- Realized today: 0.0.
- Realized total: +973.58.
- Daily loss pct: 0.0.
- Intraday drawdown pct: 0.0.
- Self-defense active: false.
- Blocked entries: 120 in scanner audit / 10 in decision audit.
- Signals found: 21.
- Visible blocked rows: 77.
- Reason coverage: 94.81%.
- Missing reason rows: 4.
- Top blocker reason: `early_entry_requires_fvg_reclaim_vwap_ema_confirmation` with 45 rows.

Operational interpretation:

- No repair was required for health/risk.
- The system was healthy, fast, and passing routine checks.
- The missed-participation pattern v2 was meant to address was present.
- Because direct v2 status later showed `latest: {}`, the correct next action was telemetry rather than another loosening.

## Latest Code Update — July 7, 2026: Risk-On Starter Participation Valve v2

Version:

- `risk-on-starter-participation-valve-2026-07-07-v2-opening-warmup`

Commits:

- `bae5ff3582f571adde8ea8cd7bb7a45ff8cf97e1`
- `07a28ed47504a2f0294b805de9351700155f8b7a`
- `98fe492e47e67aca8972ae91cc38f9da289c4502`
- `49d813b770c2d0cd3365df282a101af60c62743a`
- `ad9d8ae03e3ef4eaf972da457480ee18e794f86a`

Safety / authority impact:

- Paper-only participation overlay.
- Live trade authority remains none.
- ML live authority remains none.
- Does not bypass self-defense, risk halts, cooldowns, daily-loss, or intraday-drawdown controls.
- Does not place trades directly.
- Does not lower the global entry threshold.
- Does not open more than one risk-on starter per day.

## Earlier Critical Context

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

After Railway redeploys, run `/paper/self-check`. If the telemetry fields are present but no candidate evaluation has occurred yet, wait for the next scanner/entry cycle and check again. Do not loosen v3 further until telemetry shows the exact block reason. The next separate diagnostic cleanup remains blocker reason persistence for top blocked symbols and the persistent TEM post-harvest row so missing-reason coverage returns near 100%.
