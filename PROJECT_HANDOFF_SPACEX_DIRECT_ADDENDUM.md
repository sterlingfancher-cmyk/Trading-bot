SpaceX Direct Ticker Addendum — June 16, 2026

Purpose

Add the reported SpaceX public ticker as a direct scanner candidate while preserving all existing paper-only and risk-control guardrails.

Files changed

1. spacex_direct_overlay.py

Version:

spacex-direct-overlay-2026-06-16-v1

Route:

/paper/spacex-direct-overlay-status

Default ticker:

SPCX

Environment overrides:

* SPACEX_DIRECT_TICKER
* SPACEX_DIRECT_SECTOR

Default mapping

* Bucket: space_stocks
* Sector: XLI
* Allocation config uses the existing space_stocks bucket settings:
  * SPACE_STOCKS_ALLOC_FACTOR default 0.70
  * SPACE_STOCKS_MAX_EXPOSURE_PCT default 0.30
  * SPACE_STOCKS_MAX_POSITIONS default 3

Behavior

* Adds the ticker to UNIVERSE at startup.
* Adds the ticker to SYMBOL_SECTOR.
* Adds the ticker to SYMBOL_BUCKET.
* Ensures the space_stocks bucket exists in BUCKET_CONFIG.
* Adds the ticker to SPACEX_DIRECT and SPACE_STOCKS metadata lists.
* Requires valid price data before any entry.
* Does not force entries.
* Does not bypass risk, quality, sector, bucket, cooldown, or max-position checks.
* Does not enable live trading.
* Does not change ML authority.

Commits

* c088a50c1642005c18fd910f353d81d1fbb2b5bf
  * Added spacex_direct_overlay.py.
  * File SHA: be46d24705677a94820835957844138c0999a810.

* 60b6fbbd25093f78ffe6b82581840de442307e20
  * Wired spacex_direct_overlay into usercustomize.py startup and watchdog.
  * usercustomize.py SHA: c9ae5bdb97255b9a985994afddbb356fd3731aef.

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostic check only when intentionally debugging this overlay:

https://trading-bot-clean.up.railway.app/paper/spacex-direct-overlay-status
