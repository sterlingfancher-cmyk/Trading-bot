Theme Starter Exception Addendum — June 17, 2026

Purpose

Speed up participation in confirmed momentum themes without broadly lowering the normal entry floor.

This update allows a tiny paper-only starter when a candidate is close below the normal entry threshold, the theme/catalyst is confirmed, and risk/exposure checks remain clean.

File added

theme_starter_exception.py

Current version

theme-starter-exception-2026-06-17-v1

Route

/paper/theme-starter-exception-status

Behavior

* Wraps entry_quality_check.
* Lets the original quality check run first.
* Only considers an exception when the original quality check rejects with entry_score_below_minimum.
* Long-only.
* Paper-only by default.
* Requires allowed market mode: risk_on or constructive by default.
* Requires allowed bucket:
  * space_stocks
  * bitcoin_ai_compute
  * semi_leaders
  * data_center_infra
  * small_cap_momentum
  * precious_metals
* Requires theme or catalyst confirmation.
* Requires minimum score of 0.013 by default.
* Requires candidate to be close below the normal entry floor:
  * max gap 0.010 for most allowed buckets.
  * max gap 0.0075 for precious_metals.
* Applies starter allocation only: 0.30 alloc factor by default.
* Allows max 1 theme-starter entry per cycle by default.
* Tags allowed candidates with:
  * entry_context: theme_starter_exception
  * trade_class: theme_starter
  * theme_starter_exception metadata.

Guardrails

* Does not grant live trade authority.
* ML remains shadow-only.
* Does not raise max positions.
* Does not raise max entries per cycle.
* Does not bypass risk controls.
* Does not bypass self-defense.
* Does not bypass exposure caps.
* Does not bypass cooldown.
* Does not bypass the normal entry pipeline.
* Does not broadly lower the normal entry floor.

Runtime hooks

The module patches:

* entry_quality_check
  * Adds the controlled starter exception after the original quality check rejects for entry_score_below_minimum.

* enter_position
  * Enforces max 1 theme-starter entry per cycle.
  * Adds theme_starter_exception metadata to result, position, and latest trade row.

* try_entries_and_rotations
  * Resets the per-cycle theme-starter counter at the start of each entry cycle.

Files updated

usercustomize.py

Current version

usercustomize-theme-starter-exception-2026-06-17-v8

Startup wiring

* Registers theme_starter_exception before best_of_cycle_entry_arbitration so the arbitration preview can see the controlled starter pass.
* Re-registers theme_starter_exception from the watchdog.
* Adds optional self-check metadata for /paper/theme-starter-exception-status.

Commits

* 44fe48fc9e4211081852c4f32f985219d4a7f2b7
  * Added theme_starter_exception.py.
  * File SHA: 49db20be6de687effc3695debe7339edd965ef11.

* fa1f75896f42f1a5f004d807ab63b0658c327ba3
  * Wired theme_starter_exception into usercustomize.py startup and watchdog.
  * usercustomize.py SHA: b4f214bce9227794f39f526e00d92ba5d0d9e7da.

Expected status fields

/paper/theme-starter-exception-status should show:

* patched_entry_quality_check
* patched_enter_position
* patched_try_entries
* theme_starters_used_this_cycle
* policy.allowed_buckets
* policy.allowed_market_modes
* policy.min_score
* policy.max_score_gap
* policy.max_score_gap_precious
* policy.starter_alloc_factor
* policy.max_per_cycle

Interaction with best-of-cycle arbitration

Best-of-cycle arbitration remains active. It should now see some candidates as quality_passed=True when they qualify through theme_starter_exception_ok. It will rank eligible candidates and send only the top-ranked candidate(s) into the normal entry pipeline.

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostics only when intentionally reviewing this update

https://trading-bot-clean.up.railway.app/paper/theme-starter-exception-status

https://trading-bot-clean.up.railway.app/paper/best-of-cycle-entry-arbitration-status
