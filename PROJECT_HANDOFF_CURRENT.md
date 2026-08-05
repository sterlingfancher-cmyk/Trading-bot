# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-05 11:27 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Runtime code head covered: `a7ea21926fc6e9dd0e75b58adcce4fe261470d5d`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway project/service: `splendid-creativity / web`

This is the authoritative handoff. Older `PROJECT_HANDOFF_*` files are historical context unless this document explicitly references them.

## Executive Status

The paper bot is deployed with persistent Railway state, broad-market momentum discovery, a rules-gated ML counterfactual ledger, repaired starter participation, reconciled daily-audit telemetry, and a canonical 110-symbol boundary at the actual detailed scanner input.

The runtime remains paper-only. The existing rules engine is the sole execution authority. ML remains `shadow_recommendation_only` and cannot place orders, override a rejection, alter sizing, relax hard risk, or obtain live authority.

## Canonical Operating Links

- Routine daily audit: `/paper/daily-audit`
- Tiny self-check: `/paper/self-check`
- Targeted full diagnostics: `/paper/full-self-check`
- Paper state: `/paper/status?full=1`
- Cycle completion: `/paper/cycle-completion-contract-status`
- Persistence: `/paper/state-persistence-contract-status`
- Scanner composition: `/paper/scanner-runtime-contract-status`
- Broad discovery status: `/paper/broad-momentum-discovery-status`
- Broad candidates: `/paper/broad-momentum-candidates`
- ML Phase 2: `/paper/ml2-status`
- ML recommendation ledger: `/paper/ml-counterfactual-ledger-status`
- ML training dataset: `/paper/ml-counterfactual-training-dataset`

## Latest Live Validation

Capture time: 2026-08-05 11:26:43 CDT  
State-capture workflow run: `31023809490`  
Artifact ID: `8938324899`

Account:

- Cash: `$8,084.67`
- Equity: `$9,988.33`
- Open positions: `2`
- Positions: `AI`, `CRWD`
- Unrealized P&L: `-$11.72`
- Realized today/total: `+$0.05`
- Execution rows: `7`
- Closed results recorded: `1` win and `2` losses

Daily operational audit:

- Overall: `pass`
- Sections: `10 pass / 0 warn / 0 fail`
- Required next action: `none`
- Scanner rejection count: `17`, observed from unique rejection telemetry
- Top-five blocker reason coverage: `100%`
- Trade-journal reconciliation: `7/7` execution rows and `2/2` open positions matched

Persistence:

- Persistent mount detected: `true`
- State file: `/app/data/state.json`
- Backup: `/app/data/state.json.bak`
- State and backup exist
- In-memory richness: `[2, 7, 364, 0, 11.67]`
- On-disk richness: `[2, 7, 364, 0, 11.67]`
- Richness match: `true`
- Status refresh is observational/read-only

## Daily Audit Reconciliation — Completed

The first market-open audit exposed missing aggregate rejection counts, duplicate or blank blocker rows, absent journal-summary fields, and stale embedded persistence richness.

The repair now:

- Derives an observed unique rejected-candidate count from available scanner/decision telemetry
- Preserves exact blocker reasons and deduplicates blank duplicate rows
- Reports reason coverage explicitly
- Reconciles journal rows and positions from the authoritative runtime state when the optional summarized journal object is absent
- Labels that fallback transparently as `authoritative_runtime_state_fallback`
- Refreshes in-memory and on-disk persistence richness on every status request without saving, restoring, migrating, or repairing state

Daily-audit reconciliation version:

- `daily-audit-repair-overlay-2026-08-05-v2-reconciliation`

Persistence contract version:

- `state-persistence-contract-2026-08-05-v2-live-status`

These are reporting and observability changes only. They do not alter strategy, thresholds, sizing, risk, order paths, live authority, or ML authority.

## Broad Market Momentum Discovery — Current Architecture

Discovery sources:

- Market-wide momentum query
- Day gainers
- Most-active stocks
- Current positions
- SPY, QQQ, IWM, and DIA
- Original watchlist/theme names as bounded fallback coverage

Eligibility floors:

- Minimum price: `$3.00`
- Minimum daily volume: `350,000`
- Minimum daily dollar volume: `$10,000,000`
- Minimum market capitalization when available: `$100,000,000`

Bounds:

- Maximum retained discovery candidates: `160`
- Maximum broad-momentum slots: `80`
- Maximum base/fallback slots: `25`
- Maximum detailed-scanner input: `110`
- Discovery cache: `900 seconds`

The shared global `UNIVERSE` can temporarily exceed 110 between scans because legacy overlays append their preferred symbols. That is now telemetry, not the execution boundary. Immediately before the canonical detailed scanner runs, `scanner_runtime_contract` recomposes and enforces the bounded universe.

Latest direct evidence:

- Pre-boundary shared universe: `118`
- Actual scanner input: `110`
- Post-boundary universe: `110`
- Within policy cap: `true`
- Protected positions and benchmark ETFs retained
- Boundary phase: `pre_scan`

Do not misclassify a larger between-cycle `current_universe_count` as the scanner processing all of those names. The authoritative metric is `last_scanner_boundary.scanner_input_universe_count`.

## Scanner Ownership and Callable Chain — Repaired

The first scanner-integrity deployment used `functools.wraps` on the outer universe-boundary wrapper. That copied the inner opening-surge marker and prior-link attributes, causing telemetry to falsely report two opening-surge layers and a callable cycle.

The hotfix removes marker inheritance and preserves one canonical scanner owner.

Live scanner chain:

1. Broad-universe boundary — depth `0`
2. Opening-surge participation — depth `1`
3. Breakout participation — depth `2`
4. Market-participation accelerator — depth `3`

Validated live:

- Universe-boundary count: `1`
- Opening-surge count: `1`
- Breakout count: `1`
- Market-participation count: `1`
- Ordering: `pass`
- Boundary ordering: `pass`
- Callable cycle detected: `false`
- Chain truncated: `false`

Versions:

- Broad discovery: `broad-momentum-discovery-2026-08-05-v2.1-ownership-safe`
- Scanner contract: `scanner-runtime-contract-2026-08-05-v2.1-boundary-marker-safe`

## Source Attribution and Classification

The original source-deduplication bug treated labels such as `market_wide_momentum` as ticker symbols and could erase them. Source labels now have a dedicated deduplication path, and candidates seen in multiple discovery sources receive the intended bounded confirmation bonus.

Sector and industry enrichment is non-blocking and cached. Latest classification coverage was `20.0%` (`32/160`) with `10` cached classifications. Coverage is expected to improve gradually without delaying the trading cycle.

Latest discovery refresh retained `160` candidates from `175` eligible names. The day-gainers and most-active screens each returned `100` rows. The separate market-wide momentum query returned an HTTP 401 during this specific refresh, so the two functioning sources provided fallback coverage. Treat repeated 401 responses as a provider-capability issue requiring investigation; do not silently assume all three sources are always available.

## Cycle Health and Performance Watch

The cycle-completion contract remained healthy and not stale. The latest completed cycle took approximately `150.94` seconds. That is below the `720`-second stale threshold but materially slower than the desired routine cycle duration.

Do not loosen strategy rules in response. First determine whether the duration came from post-deployment warmup, concurrent forced discovery validation, provider retries, sector enrichment, or detailed-scanner workload. The next performance investigation should compare several ordinary market-open cycles without forced diagnostic refreshes.

## Current Effective Participation Limits

Unless a separately validated controlled-expansion state is active:

- Maximum standard starter positions: `4`
- Maximum standard starter entries per day: `3`
- Risk-on starter entries per cycle: `1`
- Normal position target: approximately `12%–18%` of equity
- Current cautious target observed: `11.475%`
- Maximum account risk per trade at the configured stop: `2%`
- Starter cash check: at least `35%` cash before another starter
- Practical post-sizing cash reserve: approximately `30%`
- Practical standard deployment ceiling: approximately `70%`
- Absolute daily-loss ceiling: `3%`
- Hard intraday drawdown halt: `2.5%`

The paper controlled-expansion layer has higher conditional ceilings. Do not treat them as normal allowances or bypass its favorable-regime and safety requirements.

## Machine Learning — Current Role

ML remains shadow recommendation only. It independently evaluates candidates and records:

- Enter, avoid, or neutral recommendation
- Probability, confidence, edge, and rank
- Rules allow/block decision and exact reason
- Executed versus counterfactual status
- 15-minute, 60-minute, end-of-day, and next-session outcomes when available
- Maximum favorable/adverse excursion
- Stop-versus-target path when available

Executed outcomes receive stronger evidence weight. Counterfactual outcomes are discounted and do not count toward promotion gates. No ML authority expansion is permitted without formal evidence and explicit user authorization.

## Proactive Performance-Improvement Directive

The assistant or engineer continuing this project must operate proactively rather than waiting for the user to identify each limitation. At the start of substantive work, independently inspect the latest live state, daily audit, scanner coverage, decision telemetry, execution results, and technical-debt signals. Surface material opportunities, bottlenecks, and failure risks before the user has to ask.

Continuously review:

- Opportunity discovery and current market leadership coverage
- Idle cash, deployment efficiency, position capacity, and concentration
- Rules-blocked candidates that later performed well and rules-approved candidates that failed
- Entry timing, extension, slippage, stop placement, profit capture, and exit leakage
- Regime changes, sector rotation, volatility, correlation, and crowding
- Provider latency, stale data, cycle duration, recursion, persistence, and deployment reliability
- ML evidence quality, selection bias, label coverage, calibration, and readiness gates
- Redundant, contradictory, misordered, or overly restrictive filters

Rank ideas by expected effect on risk-adjusted expectancy, supporting evidence, downside risk, implementation complexity, and reversibility. Prefer structural improvements over indiscriminately weakening thresholds.

Proactive analysis does not grant trading authority. Do not silently change live authority, ML authority, hard controls, strategy thresholds, or sizing. Behavioral changes should be isolated on a branch when practical, tested, reviewed for authority changes, deployed, and verified against live read-only evidence.

The standard is: diagnose the mechanism, anticipate the next bottleneck, present the highest-value improvement, and preserve safety while improving performance.

## Remaining Technical Debt and Next Priorities

1. Monitor several ordinary market-open cycles to determine why the latest completed cycle reached approximately 151 seconds.
2. Investigate repeated HTTP 401 responses from the custom market-wide momentum query while preserving day-gainer and most-active fallbacks.
3. Continue sector/industry enrichment and quantify classification coverage by cycle.
4. Compare broad-discovered candidates with original-list candidates on promotion rate, rejection reason, MFE/MAE, and realized/counterfactual outcome.
5. Reconcile the direct `/paper/runtime-shadow-capture-status` route, which remains an optional 404 in state captures while in-state runtime-shadow parity is available.
6. Continue resolving legacy architecture-ownership and typed-configuration findings. The separate refactor/governance audit remains red for pre-existing technical debt; do not misclassify that as a live Railway outage.
7. Continue accumulating ML outcomes without changing authority.

## Validation and Deployment State

Validated successful:

- Focused unit tests for audit reconciliation, persistence refresh, source attribution, universe cap, and marker isolation
- Repository safety/performance validation
- Exact Gunicorn startup smoke
- Both Railway deployment contexts
- Daily audit: pass
- Scanner runtime contract: pass
- Actual detailed-scanner input: 110
- Persistence and backup: pass
- Cycle completion: healthy/not stale

Main runtime commits:

- `7913d5e4c138757fd902731c83f8b70bec431967` — Morning audit and broad-scanner integrity upgrade
- `a7ea21926fc6e9dd0e75b58adcce4fe261470d5d` — Scanner-boundary marker-isolation hotfix

Pull requests:

- PR `#8` — Repair morning audit telemetry and enforce broad scanner integrity
- PR `#9` — Fix scanner-boundary marker inheritance

The refactor/governance audit remains red because of legacy ownership/configuration findings. Repository validation, startup smoke, Railway deployments, and the live operational contracts above passed.

## Non-Negotiable Safety Boundaries

- Paper trading only
- Rules engine remains execution authority
- ML remains shadow recommendation only
- No restoration claims for the missing historical TSM/HWM state
- No bypass of hard risk, drawdown, daily-entry, spacing, position, sector, bucket, or sizing controls
- Never infer deployment success only from a GitHub commit; verify Railway
- Never infer persistence only from code; verify `/app/data/state.json` and its backup
- Do not weaken thresholds merely to create more trades; diagnose the bottleneck first

## Next-Session Instruction

Read this document before modifying the project. Start with the latest merged `main` and fresh live state. Verify persistence, cycle completion, daily audit, scanner boundary, ML authority, and broad-discovery provider health. Preserve the user's moderate-to-aggressive risk posture while honoring the 3% daily-loss ceiling, 2% per-trade risk ceiling, and rules-gated paper-only architecture. Follow the proactive directive and do not wait for the user to discover structural limitations visible in the evidence.
