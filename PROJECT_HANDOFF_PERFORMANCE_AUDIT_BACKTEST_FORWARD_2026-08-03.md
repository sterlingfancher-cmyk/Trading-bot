# Performance Audit, Walk-Forward Backtest, and Forward Shadow Test — 2026-08-03

## Objective

Restore evidence-based performance evaluation and determine whether the paper system has become too restrictive before changing production thresholds.

## Audit conclusion from source composition

The current runtime is not governed by one entry rule. The WSGI and Gunicorn startup paths load a large collection of entry, risk, timing, volatility, quality, surge, allocation, extension, sector, fundamental, news, and position-governance overlays. Several of those layers can independently block a trade or reduce its allocation.

The most important structural risks are:

1. **Compounded score requirements** — base score floors can be raised by market mode, futures, breadth, volatility, post-loss behavior, extension logic, valuation, news, and position-quality layers.
2. **Compounded sizing reductions** — ordinary allocation, starter allocation, bucket allocation, futures reductions, breadth reductions, volatility reductions, controlled-restart sizing, and other multipliers can combine.
3. **Capacity restrictions** — daily-entry limits, per-cycle limits, maximum positions, sector limits, bucket limits, starter limits, spacing rules, and cash thresholds can all reject otherwise qualified candidates.
4. **Timing restrictions** — opening warmup, neutral starter start/end windows, late-session rules, EOD full-size rules, cooldowns, and final-30-minute blocks can leave only a narrow participation window.
5. **Composition risk** — the runtime contains multiple wrappers and watchdog-managed patches. A component-level pass does not prove that their combined behavior is performant.

## New module

`performance_audit_lab.py`

Version:

`performance-audit-lab-2026-08-03-v1`

### Restriction audit

The audit inventories active constants and callable composition for:

- scanner
- entry pipeline
- entry-quality check
- score-floor calculation
- sizing and aggression adjustment
- position entry
- exit management

It groups restrictions into:

- risk gates
- quality thresholds
- timing gates
- capacity limits
- sizing multipliers
- feature toggles

It also reads recorded rejection reasons from runtime state and identifies the functions with the deepest callable composition.

Route:

`/paper/restriction-audit`

### Historical backtest

The historical test downloads adjusted daily OHLCV data and compares three policy proxies:

1. `current_proxy` — tight participation and confirmation requirements
2. `balanced` — moderate-aggressive participation while preserving trend and risk controls
3. `permissive` — research-only high-participation profile used to quantify opportunity cost

The test reports:

- total return
- CAGR
- maximum drawdown
- Sharpe ratio
- trade count
- win rate
- profit factor
- average exposure
- time in market
- SPY and QQQ buy-and-hold benchmarks
- balanced-versus-current opportunity cost

This is a policy-proxy test, not an exact replay of every five-minute execution and provider response.

Routes:

- `/paper/performance-backtest`
- `/paper/walk-forward-backtest`

Optional query parameters:

- `period=1y`, `2y`, or another yfinance-supported period
- `symbols=35`
- `force=true`

### Formal rolling walk-forward

For each profile, the module:

1. creates rolling training and out-of-sample testing windows;
2. evaluates multiple score floors in the training window;
3. selects the best training floor using a return/drawdown/Sharpe objective;
4. applies that selected floor only to the next unseen test window;
5. combines the out-of-sample folds;
6. reports whether the profile passed the walk-forward evidence gate.

This replaces the previous proxy that always returned `formal_walk_forward_passed: false`.

### Forward-looking shadow test

Each live paper scan records top candidates and compares:

- actual execution decision
- current-policy proxy
- balanced-policy shadow decision
- permissive-policy shadow decision

It then resolves subsequent returns at:

- one hour
- same session
- one day
- three days
- five days

The forward test records MFE, MAE, missed balanced candidates, and blocker reasons. It does not place trades or change thresholds.

Route:

`/paper/performance-forward-test`

### Automatic operation

- Restriction audit runs at startup.
- Forward shadow capture runs during every entry cycle.
- Forward outcomes are updated by the watchdog.
- A two-year backtest and walk-forward run automatically after hours when the saved result is stale by 24 hours.

Status route:

`/paper/performance-audit-status`

## Composition safety

`performance_audit_composition_guard.py`

Version:

`performance-audit-composition-guard-2026-08-03-v1`

The underdeployment repair and performance audit both patch the core cycle and both have watchdogs. The composition guard propagates both ownership markers to the top callable so neither watchdog repeatedly wraps the other. This prevents wrapper growth and recursion risk.

Route:

`/paper/performance-audit-composition-status`

## Self-check integration

The all-in-one self-check gains a `performance_evidence` component with:

- backtest status
- backtest timestamp
- number of forward-test observations
- number of balanced candidates blocked by the current policy
- restriction count
- sub-1.0 sizing-factor count
- maximum callable depth
- links to the audit, backtest, and forward-test routes

## Authority boundary

The new framework is advisory and shadow-only:

- no direct order placement
- no live authority
- no ML authority
- no automatic threshold changes
- no automatic strategy changes
- no hard-risk changes

The next threshold or participation update should be based on the historical walk-forward result plus accumulating forward-shadow evidence, not on a single strong or weak market day.
