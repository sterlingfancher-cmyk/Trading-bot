Wrapper Recursion Safe Mode — June 24, 2026

Problem

The auto-runner repeatedly reported:

* last_error: maximum recursion depth exceeded
* stale_during_market: true

This continued after disabling the profit_guard_redeployment_sleeve wrapper, which indicated another try_entries_and_rotations wrapper was still likely causing recursive execution.

Action taken

The remaining wrapper-based entry arbitration module was put into diagnostic-only safe mode:

* best_of_cycle_entry_arbitration.py
* Version: best-of-cycle-entry-arbitration-2026-06-24-v2-disabled-safe-mode
* Commit: 3d6bb14c980df77b7be21c32ab31b49993ed0b74
* File SHA: 7af176395e3b7d3f7963fa038b4f11006239e03f

Current best-of-cycle behavior

* Does not patch try_entries_and_rotations by default.
* Keeps /paper/best-of-cycle-entry-arbitration-status available.
* Reports safe_mode=true.
* Reports patch_enabled=false by default.
* Reports patched_this_call.try_entries_and_rotations=false.
* Does not change live trade authority.
* Does not change ML authority.

Related prior safe-mode action

The profit-guard wrapper was already disabled:

* profit_guard_redeployment_sleeve.py
* Version: profit-guard-redeployment-sleeve-2026-06-24-v4-disabled-safe-mode
* Commit: ab424ed573afff5dc348646fd915423c8629e1e8
* File SHA: b633ae5ba274cd757d0c029a387f0fd824fc59cf

Do not re-enable these env vars in Railway without a non-wrapper rewrite:

* BEST_OF_CYCLE_ENTRY_ARBITRATION_PATCH_ENABLED
* PROFIT_GUARD_REDEPLOYMENT_SLEEVE_PATCH_ENABLED

Expected checks after Railway redeploy

1. /paper/runner-freshness

Expected:

* last_error should not show maximum recursion depth exceeded.
* stale_during_market should become false after the next successful auto cycle.
* last_successful_run_local should update.

2. /paper/best-of-cycle-entry-arbitration-status

Expected:

* version: best-of-cycle-entry-arbitration-2026-06-24-v2-disabled-safe-mode
* safe_mode: true
* patch_enabled: false
* patched_this_call.try_entries_and_rotations: false

3. /paper/profit-guard-redeployment-sleeve-status

Expected:

* version: profit-guard-redeployment-sleeve-2026-06-24-v4-disabled-safe-mode
* safe_mode: true
* patch_enabled: false
* patched_this_call.try_entries_and_rotations: false

Future implementation guidance

Do not implement future entry arbitration or profit-guard redeployment by wrapping try_entries_and_rotations again. Use one of these patterns instead:

1. Core pipeline implementation in app.py.
2. Non-wrapper pre-entry candidate selector that runs before try_entries_and_rotations.
3. Configuration-only adjustment where profit guard soft pause changes sizing rather than entry permission.

Guardrails for future work

* Do not lower entry score floors blindly.
* Do not bypass risk controls.
* Do not bypass self-defense.
* Do not bypass cooldown.
* Do not increase max positions without separate risk review.
* Keep ML shadow-only until Phase 3A requirements are met.
