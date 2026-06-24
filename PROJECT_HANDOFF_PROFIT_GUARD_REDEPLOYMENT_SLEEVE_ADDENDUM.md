Profit Guard Redeployment Sleeve Addendum — June 22-24, 2026

Purpose

Convert profit guard from a binary global new-entry shutdown into a controlled profit-protected participation mode.

The prior behavior made profit_guard_active a hard entry block in run_cycle. That protected profitable days but could also block clean dynamic-universe opportunities simply because the bot had already made money.

This addendum documents the sleeve. A normal day-profit pause can allow one small, high-quality starter candidate through the existing entry pipeline. True hard profit locks, giveback locks, risk halts, self-defense, opening warmup, and late-day cutoffs still block entries.

June 24 hotfix

A June 24 self-check showed normal midday cycles were still producing:

* profit_guard_sleeve_recursion_guard
* 100% cash
* no active self-defense
* no active profit today

That means the sleeve was still polluting the blocked-entry stack outside the intended profit-guard condition.

V3 makes the sleeve truly inert unless all of the following are true:

* new_entries_allowed is false.
* entry_block_reason contains profit_guard_active.
* profit guard is actually active in risk_controls.
* profit_guard_reason is a soft day-profit pause, not hard lock or giveback.

Normal cycles now pass through without setting a recursion flag and without generating blocked rows.

File added / updated

profit_guard_redeployment_sleeve.py

Current version

profit-guard-redeployment-sleeve-2026-06-24-v3-inert-unless-active

Route

/paper/profit-guard-redeployment-sleeve-status

Core behavior

* Patches try_entries_and_rotations.
* Remains completely inert during normal new-entry cycles.
* Does not create blocked rows unless profit guard is the active blocker.
* Only activates when new_entries_allowed is false because profit_guard_active is the active blocker.
* Does not activate when risk_halted, opening_warmup_active, self_defense_feedback_loop, or late_day_entry_cutoff is also present.
* Classifies the profit guard state from risk_controls.profit_guard_reason.
* Allows sleeve only for soft day-profit pause.
* Keeps day profit hard lock and profit giveback guard as hard blocks.
* Requires market_mode to be risk_on or constructive by default.
* Blocks when bear_confirmed is true or market_mode is risk_off, crash_warning, defensive_rotation, or bear.
* Blocks if futures action is block_opening_longs.
* Requires daily loss and intraday drawdown to be clean.
* Requires no realized loss today by default.
* Reviews up to 30 candidates.
* Allows at most one sleeve entry per day by default.
* Selects at most one candidate.
* Applies a 0.35 allocation factor by default.
* Requires the candidate to pass the normal entry_quality_check.
* Does not grant live authority.
* Does not change ML authority.

Wrapper-order behavior

V3 adds chain detection so the sleeve will not be wrapped repeatedly if it already exists inside another try_entries_and_rotations wrapper.

V3 also preserves the best-of-cycle marker when wrapping an already-patched best-of-cycle function so watchdog startup checks do not repeatedly re-wrap the chain.

Default policy

* PROFIT_GUARD_REDEPLOYMENT_SLEEVE_ENABLED=true
* PROFIT_GUARD_REDEPLOYMENT_SLEEVE_PAPER_ONLY=true
* PROFIT_GUARD_SLEEVE_MAX_REVIEWED=30
* PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY=1
* PROFIT_GUARD_SLEEVE_ALLOC_FACTOR=0.35
* PROFIT_GUARD_SLEEVE_MIN_SCORE=0.018
* PROFIT_GUARD_SLEEVE_ALLOWED_MARKET_MODES=risk_on,constructive
* PROFIT_GUARD_SLEEVE_ALLOW_SHORTS=false
* PROFIT_GUARD_SLEEVE_ALLOW_LEVERAGED_ETFS=false
* PROFIT_GUARD_SLEEVE_LEVERAGED_MIN_SCORE=0.040
* PROFIT_GUARD_SLEEVE_MAX_DAILY_LOSS_PCT=0.15
* PROFIT_GUARD_SLEEVE_MAX_INTRADAY_DRAWDOWN_PCT=0.35
* PROFIT_GUARD_SLEEVE_MAX_REALIZED_LOSS_TODAY=0.0

Important interpretation

The max daily loss and intraday drawdown settings are read in the same units used by risk_controls in state.json, where values are dashboard percentage numbers. For example, 0.35 means 0.35%, not 35%.

Allowed profit guard state

The sleeve can activate only when profit_guard_reason indicates a soft pause such as:

* day profit pause reached
* pause reached

Hard-blocked profit guard states

The sleeve remains blocked when profit_guard_reason contains:

* hard lock
* giveback
* lock triggered

Candidate rules

A candidate must:

* Not already be held.
* Not be in cooldown.
* Be long-only by default.
* Meet PROFIT_GUARD_SLEEVE_MIN_SCORE.
* Pass normal entry_quality_check.
* Pass regime_flip_entry_guard through the patched entry quality pipeline.
* Pass all normal sector and bucket exposure controls.

Leveraged ETF handling

Leveraged ETFs are blocked by the sleeve by default even if the dynamic universe can discover them. To allow them, set PROFIT_GUARD_SLEEVE_ALLOW_LEVERAGED_ETFS=true and keep the exceptional score floor at or above 0.040.

Guardrails preserved

* Does not raise max positions.
* Does not lower score thresholds.
* Does not bypass entry_quality_check.
* Does not bypass regime_flip_entry_guard.
* Does not bypass self-defense.
* Does not bypass cooldown.
* Does not bypass sector or bucket exposure caps.
* Does not bypass hard profit lock.
* Does not bypass profit giveback lock.
* Does not bypass late-day cutoff.
* Does not change ML authority.
* Does not grant live authority.

Startup wiring

usercustomize.py registers profit_guard_redeployment_sleeve after:

* dynamic_universe_builder
* theme_starter_exception
* regime_flip_entry_guard
* best_of_cycle_entry_arbitration

This order matters:

1. dynamic_universe_builder expands and validates the symbol universe.
2. theme_starter_exception can create small starter eligibility.
3. regime_flip_entry_guard blocks hostile regime/futures entries.
4. best_of_cycle_entry_arbitration ranks normally eligible candidates.
5. profit_guard_redeployment_sleeve only re-opens one capped candidate path when profit guard is a soft day-profit pause.

Commits

* 3bbf2855695fe169d634ce69a0948db208c8f5c8
  * Added profit_guard_redeployment_sleeve.py v1.
  * File SHA: b9b355aec92be772f1b3aef383e2db1c3fbef3f1.

* 6c16481628f7f7c766f42f329568f69ecb1fc6a6
  * Wired profit_guard_redeployment_sleeve into usercustomize.py startup, watchdog, and optional self-check metadata.
  * usercustomize.py SHA: ef59feaa041bdcccdccd1acebc25e6b9d29d7027.

* 77174fa6a6d2c23f2701960b95a5a65e73d8dcd7
  * Added v2 recursion guard and direct hard-block responses.
  * profit_guard_redeployment_sleeve.py SHA: 2b3ff5d702e35b257150a7859635e0a3b2306aeb.

* b6329d6729b976e8eb1b1e69ec22419e23ad157e
  * Added v3 inert-unless-active behavior and wrapper chain detection.
  * profit_guard_redeployment_sleeve.py SHA: 7fda5605a82b90b64d4676b75a75675600c25a5d.

Expected status fields

/paper/profit-guard-redeployment-sleeve-status should show:

* version: profit-guard-redeployment-sleeve-2026-06-24-v3-inert-unless-active
* patched_try_entries
* latest.status
* latest.reason
* latest.entry_block_reason
* latest.entry_blockers
* latest.profit_guard
* latest.risk_context
* latest.reviewed_count
* latest.eligible_count
* latest.selected_candidates
* latest.not_selected_count
* latest.rejected_preview
* latest.entries_returned_count
* latest.rotations_returned_count
* policy.inert_unless_profit_guard_active_blocker
* policy.normal_cycles_passthrough_without_recursion_flag

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Required follow-up after this hotfix

After Railway redeploy, check:

https://trading-bot-clean.up.railway.app/paper/runner-freshness

Expected improvement:

* last_error should not show maximum recursion depth exceeded.
* stale_during_market should become false after the next successful auto cycle.
* normal non-profit-guard cycles should no longer show profit_guard_sleeve_recursion_guard.

Optional diagnostic only when intentionally reviewing this update

https://trading-bot-clean.up.railway.app/paper/profit-guard-redeployment-sleeve-status
