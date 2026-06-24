Core Entry Pipeline Non-Wrapper Implementation — June 24, 2026

Purpose

Restore best-of-cycle candidate ranking and controlled profit-guard soft-pause redeployment without wrapping try_entries_and_rotations.

Why this was needed

The prior wrapper-based modules caused repeated auto-runner failures:

* maximum recursion depth exceeded
* stale_during_market=true

The profit_guard_redeployment_sleeve and best_of_cycle_entry_arbitration wrappers were moved into diagnostic safe mode. The next implementation needed to avoid calling or wrapping the prior try_entries_and_rotations function.

Files changed

1. core_entry_pipeline.py

* Commit: 37ac3b045c8d90d46f2719f529188f40c0ad991e
* File SHA: bc47d0166539df96cf7bf26473614b54ceca1b3b
* Version: core-entry-pipeline-2026-06-24-v1-non-wrapper

2. usercustomize.py

* Commit: a6876ecca7de8e2f02edd02d21ed4640810a1811
* File SHA: 3a6f7d11987b2314ddf59595c39ea15d5a9322cb
* Version: usercustomize-core-entry-pipeline-2026-06-24-v12

Implementation summary

core_entry_pipeline.py replaces app.try_entries_and_rotations with a complete replacement function. It does not keep, call, or wrap the prior function. This avoids recursive wrapper chains.

The replacement preserves the core app.py behavior:

* builds candidates from allowed long/short signals.
* checks already-held names.
* checks cooldown.
* respects MAX_NEW_ENTRIES_PER_CYCLE.
* calls entry_quality_check before enter_position.
* calls enter_position only after quality passes.
* uses existing weakest_position_for_rotation, rotation_allowed, latest_price, exit_position, and enter_position for rotation logic.
* does not increase max positions.
* does not bypass risk controls.
* does not change live authority.
* does not change ML authority.

Best-of-cycle behavior

The replacement ranks candidates before the entry loop using:

* raw signal score.
* theme/bucket priority.
* preferred leadership symbols.
* sector leadership alignment.
* relative-strength tags.
* breakout/reclaim tags.
* active catalyst/theme confirmation.
* minor penalty for chase/extension text.

If the cycle entry cap is reached, additional candidates are reported as not_best_of_cycle_candidate instead of being consumed silently.

Profit guard soft-pause behavior

When new_entries_allowed=false only because profit_guard_active is present, the replacement checks whether the guard is a soft day-profit pause.

Soft-pause sleeve can activate only when:

* profit guard is active.
* profit_guard_reason indicates day profit pause / pause reached.
* the reason is not hard lock, giveback, or lock triggered.
* no non-profit entry blockers are present.
* market mode is risk_on or constructive.
* market is not risk_off, crash_warning, defensive_rotation, or bear.
* futures are not block_opening_longs.
* risk controls are not halted.
* daily loss and intraday drawdown are clean.
* no more than one profit_guard_core_sleeve entry has occurred today.
* candidate is long-only.
* candidate is not already held.
* candidate is not in cooldown.
* candidate score is at least CORE_ENTRY_PROFIT_GUARD_SLEEVE_MIN_SCORE.
* candidate passes normal entry_quality_check.

The sleeve applies alloc_factor=0.35 by default and returns at most one entry.

Default env controls

* CORE_ENTRY_PIPELINE_ENABLED=true
* CORE_ENTRY_PIPELINE_PAPER_ONLY=true
* CORE_ENTRY_PIPELINE_PATCH_ENABLED=true
* CORE_ENTRY_BEST_OF_CYCLE_ENABLED=true
* CORE_ENTRY_MAX_NOT_SELECTED_ROWS=15
* CORE_ENTRY_PROFIT_GUARD_SLEEVE_ENABLED=true
* CORE_ENTRY_PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY=1
* CORE_ENTRY_PROFIT_GUARD_SLEEVE_ALLOC_FACTOR=0.35
* CORE_ENTRY_PROFIT_GUARD_SLEEVE_MIN_SCORE=0.018
* CORE_ENTRY_PROFIT_GUARD_SLEEVE_ALLOWED_MODES=risk_on,constructive
* CORE_ENTRY_PROFIT_GUARD_SLEEVE_MAX_DAILY_LOSS_PCT=0.15
* CORE_ENTRY_PROFIT_GUARD_SLEEVE_MAX_INTRADAY_DRAWDOWN_PCT=0.35

Startup wiring

usercustomize.py registers core_entry_pipeline after:

* dynamic_universe_builder
* theme_starter_exception
* regime_flip_entry_guard
* best_of_cycle_entry_arbitration safe-mode route
* profit_guard_redeployment_sleeve safe-mode route

This intentionally makes core_entry_pipeline the final owner of try_entries_and_rotations. It replaces the function rather than wrapping whichever function came before it.

Route

/paper/core-entry-pipeline-status

Expected route fields

* version: core-entry-pipeline-2026-06-24-v1-non-wrapper
* enabled: true
* paper_context: true
* patched_try_entries: true
* patched_this_call.try_entries_and_rotations
* policy.non_wrapper_replacement: true
* policy.calls_prior_try_entries: false
* policy.best_of_cycle_enabled: true
* policy.profit_guard_sleeve_enabled: true
* policy.hard_profit_lock_still_blocks: true
* policy.giveback_lock_still_blocks: true

Post-deploy validation

1. Check:

https://trading-bot-clean.up.railway.app/paper/core-entry-pipeline-status

Expected:

* version: core-entry-pipeline-2026-06-24-v1-non-wrapper
* patched_try_entries: true
* policy.non_wrapper_replacement: true
* policy.calls_prior_try_entries: false

2. Check:

https://trading-bot-clean.up.railway.app/paper/runner-freshness

Expected after next auto cycle:

* last_error: null
* stale_during_market: false
* last_successful_run_local updates

3. Check:

https://trading-bot-clean.up.railway.app/paper/self-check

Expected:

* no maximum recursion depth exceeded.
* no profit_guard_sleeve_recursion_guard.
* normal blockers should be true controls such as cooldown, entry_quality_block, extension, market state, risk controls, or not_best_of_cycle_candidate.

Important caution

Do not re-enable the old wrapper env vars:

* BEST_OF_CYCLE_ENTRY_ARBITRATION_PATCH_ENABLED
* PROFIT_GUARD_REDEPLOYMENT_SLEEVE_PATCH_ENABLED

The non-wrapper replacement should remain the only active owner of try_entries_and_rotations.
