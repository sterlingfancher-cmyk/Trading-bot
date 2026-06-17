Best-of-Cycle Entry Arbitration Addendum — June 17, 2026

Purpose

Improve candidate selection when the market is broadly green and the bot has only a limited number of new-entry slots available per cycle.

Problem addressed

The core entry pipeline can consume a limited per-cycle entry slot as soon as a candidate passes, then later candidates can be blocked by max_new_entries_per_cycle. On strong momentum days this can allow a lower-conviction passing name to take the slot before stronger theme or relative-strength names are compared.

File added

best_of_cycle_entry_arbitration.py

Current version

best-of-cycle-entry-arbitration-2026-06-17-v1

Route

/paper/best-of-cycle-entry-arbitration-status

Behavior

* Wraps try_entries_and_rotations.
* Runs only in paper context by default.
* Only acts when new entries are otherwise allowed.
* Previews visible candidate pool using the existing normal entry_quality_check.
* Does not lower score floors.
* Does not bypass cooldown.
* Does not bypass already-held checks.
* Does not bypass max-position checks.
* Does not bypass risk controls.
* Does not bypass self-defense.
* Ranks only candidates that already pass entry_quality_check.
* Sends only the top-ranked candidates into the normal entry pipeline.
* Appends non-selected passable candidates as blocked rows with reason not_best_of_cycle_candidate for audit visibility.

Ranking preference

The arbitration score keeps the raw signal score but adds small preference weights for:

* normal entry_quality_ok over controlled pullback/research starter entries.
* relative strength.
* breakout/reclaim evidence.
* theme confirmation / catalyst confirmation.
* preferred active themes:
  * space_stocks
  * bitcoin_ai_compute
  * semi_leaders
  * data_center_infra
  * small_cap_momentum
  * mega_cap_ai
  * cloud_cyber_software
  * precious_metals
* preferred momentum symbols currently under observation:
  * RKLB, RDW, LUNR, ASTS, SPCX, SATL
  * AMD, AVGO, MU, LRCX, NVTS, NBIS, GEV, STX, WDC, DELL, HPE
  * CIFR, CLSK, RIOT, HIVE, HUT, BTDR, WULF, CORZ, IREN, MARA

Important safety note

The arbitration score should not make a below-floor signal look like a normal above-floor signal. Below-floor candidates can only be selected if the existing entry_quality_check explicitly allows them, such as through the controlled pullback path.

Files updated

usercustomize.py

Current version

usercustomize-best-of-cycle-arbitration-2026-06-17-v7

Startup wiring

* Registers best_of_cycle_entry_arbitration.
* Re-registers best_of_cycle_entry_arbitration through the watchdog.
* Adds optional self-check metadata for /paper/best-of-cycle-entry-arbitration-status.

Commits

* 218812caf8e983478d5f58b189674d4dc6d040e5
  * Added best_of_cycle_entry_arbitration.py.
  * File SHA: 4dbf52c5d8603785d65fa7d41bae49d40f7055dd.

* 4c9da416540b9d2b16daf6cf14b47c2244121e56
  * Wired best_of_cycle_entry_arbitration into usercustomize.py startup and watchdog.
  * usercustomize.py SHA: 8a9f3c270939ed9a919c5fa4d9e7a550b21b6369.

Expected diagnostics after next redeploy/cycle

The latest arbitration decision is stored at:

portfolio.best_of_cycle_entry_arbitration

Expected status route fields:

* patched_try_entries
* latest.status
* latest.reviewed_count
* latest.eligible_count
* latest.selection_limit
* latest.selected_candidates
* latest.not_selected_count
* latest.not_selected_sample
* latest.rejected_preview
* latest.entries_returned_count
* latest.rotations_returned_count

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostic route only when intentionally reviewing arbitration

https://trading-bot-clean.up.railway.app/paper/best-of-cycle-entry-arbitration-status

Guardrails

* Paper-only by default.
* No live trade authority.
* ML remains shadow-only.
* Does not place trades by itself.
* Does not raise max positions.
* Does not raise max entries per cycle.
* Does not bypass risk controls.
* Does not bypass self-defense.
* Does not lower score thresholds.
* Normal entry_quality_check remains required.
