# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-05 18:39 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Runtime code head covered: `a32da49c0af582d369d2bcad813486d688fc8930`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway project/service: `splendid-creativity / web`

This is the authoritative handoff. Older `PROJECT_HANDOFF_*` files are historical context unless this document explicitly references them.

## Executive Status

The paper bot is deployed with persistent Railway state, broad-market momentum discovery, a canonical 110-symbol boundary at the actual detailed-scanner input, repaired audit and journal reconciliation, yFinance invalid-symbol hygiene, and a rules-gated ML counterfactual ledger.

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
- Provider health: `/paper/provider-health-status`
- yFinance hygiene: `/paper/yfinance-data-hygiene-status`
- ML Phase 2: `/paper/ml2-status`
- ML recommendation ledger: `/paper/ml-counterfactual-ledger-status`
- ML training dataset: `/paper/ml-counterfactual-training-dataset`

## Latest After-Market-Close Validation

Capture time: 2026-08-05 18:32:51 CDT  
State-capture workflow run: `31037930860`  
Artifact ID: `8950525999`

Daily operational audit:

- Overall: `pass`
- Sections: `10 pass / 0 warn / 0 fail`
- Required next action: `none`
- Auto-runner active and correctly skipping after the regular session
- No active error, recursion, stale cycle, halt, or self-defense state
- Scanner rejection count: `15`
- Top-five blocker reason coverage: `100%`
- Journal reconciliation: `7/7` execution rows and `2/2` open positions matched

Account at capture:

- Cash: `$8,084.67`
- Equity: `$9,976.03`
- Open positions: `AI`, `CRWD`
- Unrealized P&L: `-$24.02`
- Realized today/total: `+$0.05`
- Daily result from the recorded day-start equity: approximately `-$12.13`, or `-0.121%`

Risk remained well inside limits:

- Intraday drawdown: `0.91%`
- Absolute daily-loss ceiling: `3.0%`
- Hard intraday drawdown halt: `2.5%`
- Soft realized-loss pause: `1.0%`
- Trading halted: `false`

Persistence:

- Persistent mount detected: `true`
- State file: `/app/data/state.json`
- Backup: `/app/data/state.json.bak`
- State and backup exist
- In-memory and on-disk richness matched
- Status refresh is observational/read-only

## Highest Technical Priority — MAE/MFE Telemetry Integrity

This is now the highest technical priority and supersedes cycle-duration optimization, provider-capability investigation, and classification-coverage work until it is resolved or safely contained.

The after-close audit exposed implausible entry-relative path telemetry on completed trades. Examples include:

- A trade closed near `-3.01%` with recorded MAE near `-94.48%`
- A profitable CRWD partial exit near `+2.53%` with recorded MAE near `-95.28%`
- A MARA exit near `-0.11%` with recorded MFE near `+93.02%`

These values are not credible for the observed trades and appear to indicate a calculation, scaling, price-series, symbol-alignment, timestamp-alignment, split-adjustment, or entry-basis defect.

The immediate objective is to protect research and shadow-ML evidence quality without changing trading behavior.

Required work sequence:

1. Trace every producer and consumer of `mae_pct`, `mfe_pct`, path efficiency, stop/target path, and `ml_feature_ready`.
2. Verify symbol, side, entry price, entry timestamp, exit timestamp, interval, timezone, adjusted/unadjusted price basis, and corporate-action handling.
3. Reproduce the affected POWL, CRWD, and MARA rows from authoritative execution data and market bars.
4. Add strict invariants and provenance fields so every path label records its source bars, entry basis, time range, and calculation version.
5. Quarantine implausible or unverifiable path rows from ML training, promotion evidence, calibration, and performance conclusions.
6. Mark invalid rows as `training_eligible: false` and `ml_feature_ready: false`; never silently coerce them into plausible values.
7. Recompute or backfill historical rows only when authoritative symbol, timestamp, side, price basis, and bar data are available.
8. Add focused unit tests and a read-only integrity status surface reporting valid, invalid, quarantined, and recomputed row counts.
9. Validate the repair against live read-only evidence before allowing MAE/MFE-derived features back into the shadow training dataset.

Until this is complete:

- Do not use current MAE/MFE values to weaken or strengthen entry/exit thresholds.
- Do not use contaminated path rows as evidence for ML authority, strategy promotion, stop placement, target placement, or profit-protection changes.
- Executed trades remain rules-based.
- ML remains shadow-only.
- No hard-risk, sizing, threshold, strategy, or authority change is authorized by this priority update.

## Daily Audit Reconciliation — Completed

The audit repair now:

- Derives observed rejected-candidate counts from available decision telemetry
- Preserves exact blocker reasons and deduplicates blank duplicate rows
- Reports blocker-reason coverage explicitly
- Reconciles journal rows and positions from authoritative runtime state when the optional summarized journal object is absent
- Refreshes in-memory and on-disk persistence richness on every status request without saving, restoring, migrating, or repairing state

Versions:

- Daily audit: `daily-audit-repair-overlay-2026-08-05-v2-reconciliation`
- Persistence: `state-persistence-contract-2026-08-05-v2-live-status`

These are reporting and observability changes only.

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

The shared global `UNIVERSE` can temporarily exceed 110 between scans because legacy overlays append preferred symbols. Immediately before the canonical detailed scanner runs, `scanner_runtime_contract` recomposes and enforces the bounded universe. The authoritative metric is `last_scanner_boundary.scanner_input_universe_count`, not the between-cycle shared-universe count.

## Scanner Ownership and Callable Chain

Canonical live scanner chain:

1. Broad-universe boundary
2. Opening-surge participation
3. Breakout participation
4. Market-participation accelerator

Validated properties:

- One boundary owner
- One opening-surge layer
- One breakout layer
- One market-participation layer
- Correct ordering
- No callable cycle
- No truncated chain

Versions:

- Broad discovery: `broad-momentum-discovery-2026-08-05-v2.1-ownership-safe`
- Scanner contract: `scanner-runtime-contract-2026-08-05-v2.1-boundary-marker-safe`

## yFinance Data Hygiene — Completed and Live

The runtime now:

- Blocks known no-data symbols such as `RGIT` before provider calls
- Does not silently translate `RGIT` to `RGTI`
- Applies bounded per-symbol backoff for repeated timeout or empty responses
- Caches identical downloads briefly to reduce duplicate scanner calls
- Suppresses only the specific upstream `Timestamp.utcnow` deprecation warning from `yfinance.scrapers.quote`
- Removes quarantined symbols from broad-discovery normalization and the active universe
- Leaves valid symbols such as `CIFR` eligible after isolated transient failures

Latest after-close provider evidence:

- Successful provider requests: `6,951`
- Provider failures: `0`
- Provider timeouts: `0`
- Duplicate-request cache hits: `3,829`
- Provider circuit: closed

Commits:

- `09ea8716c43df758bdc6f6183ef2369a8a9c56eb` — invalid-symbol quarantine and request hygiene
- `a32da49c0af582d369d2bcad813486d688fc8930` — wrapper-aware provider-health telemetry

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

ML remains shadow recommendation only. It may evaluate candidates and record recommendations and outcomes, but it cannot select entries or exits, size orders, override rules, alter risk, place orders, or obtain live authority.

Executed outcomes receive stronger evidence weight. Counterfactual outcomes remain discounted and do not count toward promotion gates.

Because MAE/MFE telemetry integrity is now in question, any affected path-derived feature or label must be quarantined until verified. No ML authority expansion is permitted without formal evidence and explicit user authorization.

## Proactive Performance-Improvement Directive

The assistant or engineer continuing this project must operate proactively rather than waiting for the user to identify each limitation. At the start of substantive work, independently inspect the latest live state, daily audit, scanner coverage, decision telemetry, execution results, provider health, persistence, ML evidence quality, and technical-debt signals.

Rank ideas by expected effect on risk-adjusted expectancy, supporting evidence, downside risk, implementation complexity, and reversibility. Prefer structural improvements over indiscriminately weakening thresholds.

Proactive analysis does not grant trading authority. Do not silently change live authority, ML authority, hard controls, strategy thresholds, or sizing. Behavioral changes should be isolated, tested, reviewed for authority changes, deployed, and verified against live read-only evidence.

## Remaining Technical Debt and Priority Order

1. **Repair or quarantine MAE/MFE and path-label telemetry.** This is the active highest priority.
2. Verify that contaminated path features are excluded from every shadow-ML training and promotion surface until corrected.
3. Monitor several ordinary market-open cycles and quantify scanner/provider/runtime duration without forced diagnostic refreshes.
4. Investigate repeated HTTP 401 responses from the custom market-wide momentum query while preserving day-gainer and most-active fallbacks.
5. Continue sector/industry enrichment and quantify classification coverage by cycle.
6. Compare broad-discovered and original-list candidates using only trustworthy outcome labels.
7. Evaluate the profit-giveback guard after more evidence; do not change it from one day of results.
8. Reconcile the optional `/paper/runtime-shadow-capture-status` 404 while preserving in-state runtime-shadow parity.
9. Continue resolving legacy architecture-ownership and typed-configuration findings.
10. Continue accumulating valid ML outcomes without changing authority.

## Validation and Deployment State

Validated successful:

- Repository safety/performance validation
- Exact Gunicorn startup smoke
- Both Railway deployment contexts
- Daily audit: pass
- Scanner runtime contract: pass
- Actual detailed-scanner input bounded at 110
- Persistence and backup: pass
- Cycle completion: healthy/not stale
- Provider health and yFinance hygiene: pass

The separate refactor/governance audit remains red because of legacy ownership/configuration findings. Do not misclassify that as a live Railway outage.

## Non-Negotiable Safety Boundaries

- Paper trading only
- Rules engine remains execution authority
- ML remains shadow recommendation only
- No restoration claims for missing historical TSM/HWM state
- No bypass of hard risk, drawdown, daily-entry, spacing, position, sector, bucket, or sizing controls
- Never infer deployment success only from a GitHub commit; verify Railway
- Never infer persistence only from code; verify `/app/data/state.json` and its backup
- Do not weaken thresholds merely to create more trades; diagnose the mechanism first
- Do not train on, promote from, or optimize against telemetry that has failed integrity checks

## Next-Session Instruction

Read this document before modifying the project. Begin with the MAE/MFE integrity investigation and protect the ML evidence pipeline before performance tuning. Start from the latest merged `main` and fresh live state. Verify persistence, cycle completion, daily audit, scanner boundary, provider health, ML authority, and broad-discovery status. Preserve the user's moderate-to-aggressive risk posture while honoring the 3% daily-loss ceiling, 2% per-trade risk ceiling, and rules-gated paper-only architecture.