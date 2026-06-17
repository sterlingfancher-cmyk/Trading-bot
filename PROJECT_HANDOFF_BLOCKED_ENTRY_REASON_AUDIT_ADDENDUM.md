Blocked Entry Reason Audit Addendum — June 17, 2026

Purpose

Answer the operator question: "The market is green; why no trades?"

This update adds a mobile-safe advisory audit that reads existing state/scanner audit data and summarizes blocked entries, rejected candidates, top blocked symbols, likely blocker categories, and watched momentum symbols. It is intended to make the routine /paper/self-check more useful without running heavy diagnostic routes.

Files added

1. blocked_entry_reason_audit.py

Version:

blocked-entry-reason-audit-2026-06-17-v1

Route:

/paper/blocked-entry-reason-audit-status

Behavior:

* Reads existing state/scanner audit data.
* Summarizes visible blocked-entry rows.
* Counts top blocked symbols.
* Counts top blocker reasons.
* Groups reasons into categories such as:
  * extension_chase
  * quality_score
  * max_positions
  * sector_or_bucket_exposure
  * cooldown
  * missing_or_stale_price
  * risk_control
  * cash_gate
  * market_context
  * already_open
* Watches current momentum themes including space, AI/semis/data center, storage/hardware, and crypto/compute.
* Reports watched momentum symbols seen or blocked.
* Does not call heavy market-data routes.
* Does not place trades.
* Does not lower thresholds.
* Does not change live or ML authority.

2. blocked_entry_reason_selfcheck_overlay.py

Version:

blocked-entry-reason-selfcheck-overlay-2026-06-17-v1

Route:

/paper/blocked-entry-reason-selfcheck-overlay-status

Behavior:

* Wraps self_check.run_self_check.
* Injects blocked_entry_reason_audit into dashboard.blocked_entry_reason_audit.
* Adds blocked_entry_reason_audit_summary at the top level of /paper/self-check.
* Adds operator_summary fields:
  * blocked_entry_no_trade_read
  * blocked_entry_top_categories
  * blocked_entry_top_reasons
  * blocked_entry_top_symbols
  * watched_momentum_symbols_seen
  * watched_momentum_symbols_blocked
* Keeps the routine one-link policy intact.

Files updated

usercustomize.py

Version:

usercustomize-blocked-entry-reason-audit-2026-06-17-v6

Startup wiring:

* Registers blocked_entry_reason_audit.
* Registers blocked_entry_reason_selfcheck_overlay.
* Re-registers both from the watchdog.
* Adds optional self-check metadata for:
  * /paper/blocked-entry-reason-audit-status
  * /paper/blocked-entry-reason-selfcheck-overlay-status

Commits

* d5e154c54588f82f0dd0992fc6f97c0cbe3401ee
  * Added blocked_entry_reason_audit.py.
  * File SHA: c5f93f01836f04a386ae99a4a99706ce5bab391f.

* 14a93b40273867d7058867fc1563caa7e0d00887
  * Added blocked_entry_reason_selfcheck_overlay.py.
  * File SHA: cffde3959b9f87e998bbbbf24f06e3b892b10e99.

* 4ae8e0a20c25d3b824bf2384ceb0798101074cef
  * Wired both modules into usercustomize.py startup and watchdog.
  * usercustomize.py SHA: e379a1aea6528539b4a2a64397c2e1ca9de5c0b8.

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Expected new self-check fields after redeploy

* dashboard.blocked_entry_reason_audit
* blocked_entry_reason_audit_summary
* operator_summary.blocked_entry_no_trade_read
* operator_summary.blocked_entry_top_categories
* operator_summary.blocked_entry_top_reasons
* operator_summary.blocked_entry_top_symbols
* operator_summary.watched_momentum_symbols_seen
* operator_summary.watched_momentum_symbols_blocked

Optional diagnostic routes only when intentionally debugging

https://trading-bot-clean.up.railway.app/paper/blocked-entry-reason-audit-status

https://trading-bot-clean.up.railway.app/paper/blocked-entry-reason-selfcheck-overlay-status

Guardrails

* Advisory only.
* Paper-only diagnostics.
* No live trade authority.
* ML remains shadow-only.
* Does not place trades.
* Does not lower thresholds.
* Does not bypass risk controls.
