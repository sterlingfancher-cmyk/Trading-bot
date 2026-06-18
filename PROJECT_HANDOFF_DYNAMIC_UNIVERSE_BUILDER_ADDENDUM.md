Dynamic Universe Builder Addendum — June 18, 2026

Purpose

Move the bot away from a narrow, hand-built-only scanner universe without trying to scan every public ticker symbol.

This update adds a capped dynamic discovery funnel. It keeps the existing curated universe but adds a broader session candidate pool from theme baskets, current state/scanner context, shadow/missed-mover observations, and optional configured extra symbols. Only liquid, valid, active candidates are promoted into the paper scanner.

File added

dynamic_universe_builder.py

Current version

dynamic-universe-builder-2026-06-18-v1

Routes

/paper/dynamic-universe-builder-status

/paper/dynamic-universe

Core behavior

* Patches scan_signals.
* Before each scan cycle, refreshes/promotes a dynamic symbol universe using a 15-minute cache by default.
* Starts with the original app.py UNIVERSE as the stable base.
* Adds symbols from broad theme baskets.
* Adds symbols discovered in recent scanner audit, speculative momentum observations, ML shadow observations, and current open positions.
* Adds optional configured symbols from DYNAMIC_UNIVERSE_EXTRA_SYMBOLS.
* Downloads 30-day daily price/volume data through yfinance.
* Requires valid price/volume/liquidity before promotion.
* Scores candidates using 1-day move, 5-day move, relative volume, dollar volume, and theme priority.
* Promotes only the top scored candidates into core.UNIVERSE.
* Updates SYMBOL_SECTOR, SYMBOL_BUCKET, and BUCKET_CONFIG for promoted dynamic candidates.
* Stores diagnostics in portfolio.dynamic_universe_builder.

Default caps and filters

* Max seed symbols: 260.
* Max promoted symbols: 75.
* Max total scanner universe: 180.
* Cache TTL: 900 seconds.
* Minimum price: $3.
* Minimum average volume: 350,000 shares.
* Minimum dollar volume: $5,000,000.
* Minimum 1-day move: 1.25%, or stronger 5-day move.
* Minimum relative volume ratio: 1.15.
* Minimum promotion score: 0.28.

Theme baskets added

* semi_leaders
* memory_storage
* data_center_infra
* bitcoin_ai_compute
* ai_software_momentum
* space_stocks
* small_cap_momentum
* biotech_speculative
* industrial_power
* leveraged_etf_watch

Important new coverage examples

* LRCX
* AMAT
* KLAC
* ASML
* QCOM
* HIVE
* BE
* DRAM
* SOXL
* GEV
* WDC
* MRVL
* MU
* CIFR

Leveraged ETF handling

SOXL and other leveraged ETFs are placed in leveraged_etf_watch.

Default leveraged ETF limits:

* Allowed in discovery by default.
* Max promoted leveraged ETFs: 2.
* Bucket allocation factor: 0.25.
* Max exposure: 8%.
* Max positions: 1.

This does not force SOXL entries. It only makes it discoverable and scoreable if it passes liquidity, move, and volume filters. Existing quality/risk/regime guards still apply.

Guardrails

* Does not place trades.
* Does not grant live authority.
* Does not change ML authority.
* Does not lower entry thresholds.
* Does not bypass entry quality checks.
* Does not bypass regime_flip_entry_guard.
* Does not bypass self-defense.
* Does not bypass cooldown.
* Does not bypass exposure caps.
* Existing scanner, theme-starter, regime guard, and best-of-cycle arbitration remain downstream.

Files updated

usercustomize.py

Current version

usercustomize-dynamic-universe-builder-2026-06-18-v10

Startup wiring

Dynamic universe builder is registered before:

* theme_starter_exception
* regime_flip_entry_guard
* best_of_cycle_entry_arbitration

This order matters:

1. dynamic_universe_builder expands the candidate universe.
2. theme_starter_exception can create small starter eligibility when appropriate.
3. regime_flip_entry_guard blocks unsafe entries during hostile futures/regime conditions.
4. best_of_cycle_entry_arbitration ranks only still-eligible candidates.

Commits

* 2d7aa5c05b491f39699d8e71358613b8e40db3ff
  * Added dynamic_universe_builder.py.
  * File SHA: d4e0ba459468d7aaefb93ec9e8c04acda665c5d6.

* d5d3ccc85234db6e3570ba652c2c5b46e677454f
  * Wired dynamic_universe_builder into usercustomize.py startup, watchdog, and optional self-check metadata.
  * usercustomize.py SHA: 65f835e1c65c7c968dd3b4823f8784d3447e4520.

Expected status fields

/paper/dynamic-universe-builder-status should show:

* patched_scan_signals
* seed_count
* base_universe_count
* promoted_count
* final_universe_count
* promoted_symbols
* top_promoted
* top_rejected
* policy.max_seed_symbols
* policy.max_promoted_symbols
* policy.max_total_universe
* policy.min_price
* policy.min_avg_volume
* policy.min_dollar_volume
* policy.min_move_pct
* policy.min_volume_ratio
* policy.min_promotion_score
* policy.allow_leveraged_etfs
* policy.leveraged_max_promoted
* policy.cache_ttl_seconds

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostic only when intentionally reviewing this update

https://trading-bot-clean.up.railway.app/paper/dynamic-universe-builder-status

Optional force-refresh diagnostic

https://trading-bot-clean.up.railway.app/paper/dynamic-universe-builder-status?force=1
