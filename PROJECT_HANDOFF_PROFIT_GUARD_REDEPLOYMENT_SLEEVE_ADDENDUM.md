Profit Guard Redeployment Sleeve Addendum — June 22-24, 2026

Purpose

Convert profit guard from a binary global new-entry shutdown into a controlled profit-protected participation mode.

Current production decision

The wrapper-based profit guard sleeve is disabled in safe mode. The diagnostic route remains available, but the module no longer patches try_entries_and_rotations by default.

Why disabled

Live runner freshness checks continued to show:

* last_error: maximum recursion depth exceeded
* stale_during_market: true

This persisted after v2 recursion guards and v3 inert-unless-active behavior. The failure mode was tied to wrapper chaining around try_entries_and_rotations, likely involving best_of_cycle_entry_arbitration and the startup watchdog re-registration pattern.

The correct near-term safety action is to remove the sleeve from the live entry path and restore auto-runner stability. Future profit-guard participation should be implemented inside the core entry pipeline or via a non-wrapper hook, not with another try_entries_and_rotations wrapper.

File

profit_guard_redeployment_sleeve.py

Current version

profit-guard-redeployment-sleeve-2026-06-24-v4-disabled-safe-mode

Route

/paper/profit-guard-redeployment-sleeve-status

Current behavior

* Does not patch try_entries_and_rotations by default.
* Does not change live trade authority.
* Does not change ML authority.
* Keeps diagnostic route available.
* Reports safe_mode=true.
* Reports patch_enabled=false by default.
* Reports enabled=false.
* Preserves policy documentation for the desired future sleeve behavior.

Critical safe-mode default

PROFIT_GUARD_REDEPLOYMENT_SLEEVE_PATCH_ENABLED=false

Do not enable this in Railway unless a non-recursive implementation has been tested. The old wrapper approach caused auto-runner recursion failures.

History

V1 added a profit-guard participation sleeve.

* Commit: 3bbf2855695fe169d634ce69a0948db208c8f5c8
* File SHA: b9b355aec92be772f1b3aef383e2db1c3fbef3f1

V2 added recursion guards.

* Commit: 77174fa6a6d2c23f2701960b95a5a65e73d8dcd7
* File SHA: 2b3ff5d702e35b257150a7859635e0a3b2306aeb

V3 made the sleeve inert unless profit guard was the active blocker.

* Commit: b6329d6729b976e8eb1b1e69ec22419e23ad157e
* File SHA: 7fda5605a82b90b64d4676b75a75675600c25a5d

V4 disabled the runtime wrapper by default to restore auto-runner stability.

* Commit: ab424ed573afff5dc348646fd915423c8629e1e8
* File SHA: b633ae5ba274cd757d0c029a387f0fd824fc59cf

Expected status fields

/paper/profit-guard-redeployment-sleeve-status should show:

* version: profit-guard-redeployment-sleeve-2026-06-24-v4-disabled-safe-mode
* enabled: false
* patch_enabled: false
* safe_mode: true
* patched_this_call.try_entries_and_rotations: false
* policy.wrapper_disabled_by_default: true
* policy.does_not_patch_try_entries_by_default: true
* policy.future_fix_required: implement_inside_core_entry_pipeline_or_non_wrapper_hook

Routine post-deploy check

Use:

https://trading-bot-clean.up.railway.app/paper/runner-freshness

Expected improvement after Railway redeploy and next auto cycle:

* last_error should not show maximum recursion depth exceeded.
* stale_during_market should become false after the next successful auto cycle.
* last_successful_run_local should update.

Then use:

https://trading-bot-clean.up.railway.app/paper/self-check

Expected self-check improvement:

* no profit_guard_sleeve_recursion_guard rows.
* normal entry blockers should show cooldown, extension, market quality, risk controls, or other real blockers.

Future implementation recommendation

Do not revive the wrapper. Build one of these instead:

1. Core pipeline implementation: adjust run_cycle so profit_guard_active distinguishes soft pause, hard lock, and giveback lock before new_entries_allowed is set.
2. Non-wrapper pre-entry hook: produce a filtered candidate list before try_entries_and_rotations is called, without wrapping the function.
3. Configuration-only fallback: raise the hard lock threshold or convert only the soft day-profit pause threshold to a sizing reduction inside app.py.

Guardrails for future implementation

* Keep hard profit lock and giveback lock as hard blocks.
* Keep self-defense, risk halt, opening warmup, and late-day cutoff as hard blocks.
* Do not lower score floors.
* Do not bypass entry_quality_check.
* Do not bypass regime_flip_entry_guard.
* Do not bypass cooldown.
* Do not increase max positions without separate risk review.
* Keep ML shadow-only.
