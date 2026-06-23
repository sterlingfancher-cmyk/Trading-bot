Profit Guard Redeployment Sleeve Addendum — June 22-23, 2026

Purpose

Convert profit guard from a binary global new-entry shutdown into a controlled profit-protected participation mode.

The prior behavior made profit_guard_active a hard entry block in run_cycle. That protected profitable days but could also block clean dynamic-universe opportunities simply because the bot had already made money.

This addendum documents the new sleeve. A normal day-profit pause can allow one small, high-quality starter candidate through the existing entry pipeline. True hard profit locks, giveback locks, risk halts, self-defense, opening warmup, and late-day cutoffs still block entries.

June 23 hotfix

A runner freshness check showed:

* last_error: maximum recursion depth exceeded
* stale_during_market: true
* profit guard sleeve status route was present, but patched_try_entries was false

The likely failure mode was wrapper-order recursion between profit_guard_redeployment_sleeve and best_of_cycle_entry_arbitration around try_entries_and_rotations.

V2 adds explicit recursion protection and conservative blocked responses so a wrapper-order problem cannot keep the auto-runner failing repeatedly. In hard-block profit states, the sleeve no longer delegates back into the wrapper chain just to produce blocked rows.

File added / updated

profit_guard_redeployment_sleeve.py

Current version

profit-guard-redeployment-sleeve-2026-06-23-v2-recursion-guard

Route

/paper/profit-guard-redeployment-sleeve-status

Core behavior

* Patches try_entries_and_rotations.
* Only activates when new_entries_allowed is false because profit_guard_active is the active blocker.
* Does not activate when risk_halted, opening_warmup_active, self_defense_feedback_loop, or late_day_entry_cutoff is also present.
* Classifies the profit guard state from risk_controls.profit_guard_reason.
* Allows sleeve only for soft day-profit pause.
* Keeps day profit hard lock and profit giveback guard as hard blocks.
* For hard-block states, returns conservative blocked rows directly instead of delegating back into the wrapper chain.
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

Recursion guard behavior

V2 adds:

* in-progress guard around passthrough calls.
* RecursionError catch during normal passthrough.
* RecursionError catch during sleeve attempts.
* Direct conservative blocked response when a hard block is already active.
* Status detection that can recognize the sleeve when it is wrapped inside best-of-cycle arbitration.

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

Expected status fields

/paper/profit-guard-redeployment-sleeve-status should show:

* version: profit-guard-redeployment-sleeve-2026-06-23-v2-recursion-guard
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
* policy.max_reviewed
* policy.max_entries_per_day
* policy.alloc_factor
* policy.min_score
* policy.allowed_market_modes
* policy.allow_shorts
* policy.allow_leveraged_etfs
* policy.leveraged_min_score
* policy.hard_profit_lock_still_blocks
* policy.giveback_lock_still_blocks

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Required follow-up after this hotfix

After Railway redeploy, check:

https://trading-bot-clean.up.railway.app/paper/runner-freshness

Expected improvement:

* last_error should clear on the next successful run, or at minimum no longer show maximum recursion depth exceeded after the next auto cycle.
* stale_during_market should become false after the next successful auto cycle.

Optional diagnostic only when intentionally reviewing this update

https://trading-bot-clean.up.railway.app/paper/profit-guard-redeployment-sleeve-status
