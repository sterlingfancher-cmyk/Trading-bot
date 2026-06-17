Regime Flip Entry Guard Addendum — June 17, 2026

Purpose

Reduce clustered losses caused by adding or holding too much long exposure when the market looks green on the surface but futures/regime conditions are deteriorating.

This update was prompted by the June 17 afternoon test where IWM, QQQ, SPY, and UCTT all exited with market_regime_protection after the book flipped risk_off.

File added

regime_flip_entry_guard.py

Current version

regime-flip-entry-guard-2026-06-17-v1

Route

/paper/regime-flip-entry-guard-status

Behavior

Entry protection

* Wraps entry_quality_check.
* Lets the current quality pipeline run first.
* Blocks fresh long entries after they otherwise pass if the guard detects hostile regime/futures context.
* Blocks fresh longs in hostile market modes:
  * risk_off
  * crash_warning
  * defensive_rotation
* Blocks fresh longs when futures action is block_opening_longs.
* Blocks benchmark ETF entries when futures are hostile.
* Blocks benchmark ETF entries when market extension guard is reducing aggression or protecting against chase conditions.
* Enforces a benchmark ETF exposure cap of 40% by default.
* Blocks overextended leader entries unless they are starter-sized or pullback/reclaim entries.

Final entry protection

* Wraps enter_position as a second safety net.
* Re-checks the same regime/futures/ETF/overextension rules immediately before entry placement.
* Tags accepted entries with regime_flip_entry_guard metadata.

Preemptive trim protection

* Wraps manage_exits.
* When futures flip hostile before the core market mode fully changes to risk_off, trims vulnerable long positions by 50% by default.
* Vulnerable positions include:
  * benchmark ETF positions
  * positions marked overextended by multi-timeframe metadata.
* Does not duplicate trims; each position is marked after one preemptive trim.
* Core risk_off full exits still remain handled by existing market_regime_protection logic.

Default policy

* Paper-only by default.
* Enabled by default.
* Preemptive trim enabled by default.
* Preemptive trim fraction: 0.50.
* Benchmark ETF exposure cap: 40%.
* Overextended daily threshold: 15% from 20DMA.
* Starter max alloc factor for overextended exception: 0.35.
* Benchmark ETFs watched by default:
  * SPY
  * QQQ
  * IWM
  * SMH
  * DIA
  * RSP
  * ARKK

Guardrails

* Does not grant live trade authority.
* ML remains shadow-only.
* Does not raise max positions.
* Does not raise max entries per cycle.
* Does not lower score thresholds.
* Does not bypass core risk controls.
* Does not bypass self-defense.
* Does not bypass core market_regime_protection exits.

Files updated

usercustomize.py

Current version

usercustomize-regime-flip-entry-guard-2026-06-17-v9

Startup wiring

* Registers regime_flip_entry_guard after theme_starter_exception.
* Registers regime_flip_entry_guard before best_of_cycle_entry_arbitration.
* This order allows theme_starter_exception to create a small eligible starter, then lets regime_flip_entry_guard block it if futures/regime conditions are hostile, then lets best_of_cycle_entry_arbitration rank only still-eligible candidates.
* Re-registers regime_flip_entry_guard through the watchdog.
* Adds optional self-check metadata for /paper/regime-flip-entry-guard-status.

Commits

* d1153e0bc17e3a048ed326aad33ee0c292d9b350
  * Added regime_flip_entry_guard.py.
  * File SHA: d220d1121c8216b230089dd19d6d5b35dcd91b1a.

* 03faccc2a92a920c92c042d44db9aa98598dbc3d
  * Wired regime_flip_entry_guard into usercustomize.py startup and watchdog.
  * usercustomize.py SHA: baa553ae8f9fee618ed0d905e644be7089a66329.

Expected status fields

/paper/regime-flip-entry-guard-status should show:

* patched_entry_quality_check
* patched_enter_position
* patched_manage_exits
* latest
* policy.benchmark_etfs
* policy.benchmark_etf_cap_pct
* policy.hostile_futures_actions
* policy.hard_block_futures_actions
* policy.hostile_market_modes
* policy.overextended_daily_pct
* policy.starter_max_alloc_factor
* policy.preemptive_trim_enabled
* policy.preemptive_trim_fraction

Expected future blocked reasons

* regime_flip_block_fresh_long
* futures_block_opening_longs_guard
* benchmark_etf_futures_hostile_block
* benchmark_etf_market_extension_block
* benchmark_etf_regime_cap
* overextended_leader_requires_starter_or_pullback_reclaim

Expected future partial-exit reason

* regime_flip_preemptive_trim

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostic only when intentionally reviewing this guard

https://trading-bot-clean.up.railway.app/paper/regime-flip-entry-guard-status

Optional interaction checks

https://trading-bot-clean.up.railway.app/paper/theme-starter-exception-status

https://trading-bot-clean.up.railway.app/paper/best-of-cycle-entry-arbitration-status
