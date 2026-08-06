# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-06 14:08 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Runtime code head covered: `d9a93e9cb63ec3e227e08d7c090ff070c2327fa3`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway project/service: `splendid-creativity / web`

This is the authoritative handoff. Older `PROJECT_HANDOFF_*` files are historical context unless this document explicitly references them.

## Executive Status

The paper bot remains deployed with persistent Railway state, broad-market momentum discovery, a canonical 110-symbol boundary at the actual detailed-scanner input, reconciled audit/journal reporting, protected-symbol market-data hygiene, exact-lifecycle MAE/MFE containment, and a rules-gated ML counterfactual ledger.

The runtime remains paper-only. The existing rules engine is the sole execution authority. ML remains `shadow_recommendation_only` and cannot place orders, select or override entries/exits, alter sizing, relax hard risk, change thresholds, or obtain live authority.

The MAE/MFE integrity incident is safely contained but not fully closed. Legacy or unverifiable path rows remain quarantined and training-ineligible. Completion still requires trustworthy forward evidence from at least one newly opened and completed exact-lifecycle trade.

## Latest Runtime Change

PR `#15`, **Compact daily audit and finalize integrity reporting**, was squash-merged into `main` as:

- Runtime commit: `d9a93e9cb63ec3e227e08d7c090ff070c2327fa3`
- Data-integrity audit overlay: `daily-data-integrity-audit-overlay-2026-08-06-v2-compact-finalizer`

The update is reporting and observability only. It does not change strategy, entry/exit rules, scoring thresholds, sizing, hard-risk controls, order placement, live authority, or ML authority.

Implemented behavior:

- `/paper/daily-audit` now returns a compact operator summary by default.
- `/paper/daily-audit?full=1` preserves the complete diagnostic payload.
- The route performs a final reconciliation after all wrapper layers so section `10b_market_data_and_path_integrity` is included in the conclusion totals.
- The complete audit now contains 13 section objects: 11 operational checks, `11_conclusion`, and `12_next_action`.
- `11_conclusion.checked_sections` must equal `11`.
- MAE/MFE reporting now exposes explicit integer counts for valid, invalid/quarantined, training-eligible, enriched, quarantined, and recomputed rows rather than null placeholders.
- Forward-validation and historical-backfill states are reported separately.
- `net_daily_loss_pct` is now the preferred operator label. The legacy `realized_loss_pct` key remains for compatibility and is explicitly identified as sourced from the runtime daily-loss metric.
- The GitHub daily-audit workflow now requests `?full=1` and validates the 11-check/13-object contract.

Focused regression validation passed `3/3`. Both Railway deployment contexts reported success for commit `d9a93e9`:

- `splendid-creativity / web`: success
- `dazzling-dedication / Trading-bot`: success

The custom `daily-operational-audit` push-workflow status had not yet surfaced through the available GitHub connector when this handoff was published. Do not treat its absence as a failure; verify the workflow or the live endpoints before claiming final post-deployment contract validation.

## Canonical Operating Links

- Routine compact daily audit: `/paper/daily-audit`
- Complete daily audit: `/paper/daily-audit?full=1`
- Data-integrity audit status: `/paper/data-integrity-audit-status`
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
- Intratrade path integrity: `/paper/intratrade-path-integrity-status`
- MAE/MFE integrity: `/paper/mae-mfe-integrity-status`
- ML Phase 2: `/paper/ml2-status`
- ML recommendation ledger: `/paper/ml-counterfactual-ledger-status`
- ML training dataset: `/paper/ml-counterfactual-training-dataset`

## Latest Afternoon Operational Baseline

Capture time: 2026-08-06 13:46:56 CDT  
This baseline was captured immediately before the compact-audit update. It established that the underlying runtime was healthy and the integrity containment layer was live.

Daily operational audit:

- Overall: `pass`
- Reported sections at capture: `10 pass / 0 warn / 0 fail`
- Known reporting defect at capture: section `10b` was present and passing but omitted from the conclusion count
- Correct reconciled expectation after the update: `11 pass / 0 warn / 0 fail`
- Required next action: `none`
- Audit duration: `0.225` seconds
- External provider calls from the audit route: `0`
- Trading actions from the audit route: `0`
- Repair actions from the audit route: `0`

Account at capture:

- Cash: `$9,964.09`
- Equity: `$9,964.09`
- Open positions: `0`
- Realized today: `-$35.97`
- Realized total: `-$35.92`
- Unrealized P&L: `$0.00`
- Wins/losses: `1 / 4`

The runtime daily-loss metric was `0.12%`, and intraday drawdown was `0.12%`. These were well inside all limits:

- Soft daily-loss pause: `1.0%`
- Hard realized-loss halt: `2.5%`
- Hard intraday drawdown halt: `2.5%`
- Absolute daily-loss ceiling: `3.0%`
- Trading halted: `false`
- Self-defense active: `false`

Auto-runner:

- Enabled: `true`
- Worker thread observed active: `true`
- Last completed cycle status: `completed`
- Last completed cycle duration: `64.353` seconds
- Active cycles at audit time: `0`
- Stale cycle: `false`
- Cycle error: `none`

Scanner and decision telemetry:

- Signals found: `3`
- Entries: `0`
- Unique rejected signals: `18`
- Blocker reason coverage: `100%`
- Top blockers included `entry_quality_block`, `loss_streak_defensive_governor`, and `extended_below_5m_ma20`
- No threshold relaxation was justified by this result

Journal and persistence:

- Execution rows: `9/9` matched
- Open positions: `0/0` matched
- Persistent mount detected: `true`
- State file: `/app/data/state.json`
- Backup: `/app/data/state.json.bak`
- In-memory and on-disk richness matched
- Status refresh remained observational/read-only

Market-data integrity:

- Provider requests: `4,602`
- Provider successes: `4,602`
- Provider failures: `0`
- Provider timeouts: `0`
- Empty responses: `0`
- Provider circuit: closed
- Protected benchmark symbols blocked: `0`
- Active contaminated MAE/MFE features: `0`

## MAE/MFE Integrity — Current State

The original defect involved implausible entry-relative path telemetry on completed trades, including approximately `-95%` MAE or `+93%` MFE readings that were not credible for the observed executions.

The current runtime now:

- Uses symbol-specific position data and exact lifecycle identity
- Binds path identity to symbol, side, entry timestamp, and entry price
- Resets capture when the position fingerprint changes
- Rejects implausible price observations and path bounds
- Prevents protected symbols and isolated provider failures from cascading into broad quarantine
- Disables legacy symbol-only feature matching
- Quarantines unverifiable path and feature rows
- Forces invalid rows to `training_eligible: false` and `ml_feature_ready: false`
- Prevents active contaminated features from appearing as a clean daily-audit pass

Afternoon evidence:

- Invalid or quarantined path rows: `4`
- Training-eligible path rows: `0`
- Active contaminated feature rows: `0`
- Integrity resets: `0`
- Integration error: `none`

Interpretation:

- **Containment is complete.** Questionable rows are not active ML evidence.
- **Forward validation is pending.** No newly completed exact-lifecycle trade has yet established a trustworthy valid path row.
- **Historical repair/backfill is not established.** Recompute historical records only when authoritative symbol, side, entry/exit timestamps, entry basis, and source bars are available.
- Keep MAE/MFE-derived features excluded from threshold tuning, stop/target changes, strategy promotion, and ML authority decisions until forward validation succeeds.

## Daily Audit Contract

Routine operator use should call `/paper/daily-audit`. The compact payload contains:

- Overall and section totals
- Account/equity and daily performance
- Runner and active-error state
- Risk/halt state
- Signals, entries, rejections, and top blockers
- Journal/persistence reconciliation
- Provider and MAE/MFE integrity
- Required next action
- Link to the complete audit

Automated validation, detailed diagnosis, and archival capture should call `/paper/daily-audit?full=1`.

Required invariants:

- Compact response type: `daily_operational_audit_compact`
- Full response type: `daily_operational_audit`
- Full section-object count: `13`
- Operational checked-section count: `11`
- Integrity section key: `10b_market_data_and_path_integrity`
- Audit route performs no provider fan-out, trading action, repair action, or heavy research
- Audit authority remains reporting-only

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
- Discovery cache: `900` seconds

The shared global `UNIVERSE` may temporarily exceed 110 between scans because legacy overlays append preferred symbols. Immediately before the canonical detailed scanner runs, `scanner_runtime_contract` recomposes and enforces the bounded universe. The authoritative metric is `last_scanner_boundary.scanner_input_universe_count`.

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

## yFinance and Provider Hygiene

The runtime:

- Blocks known no-data symbols such as `RGIT` before provider calls
- Does not silently translate `RGIT` to `RGTI`
- Applies bounded per-symbol backoff for repeated timeout or empty responses
- Caches identical downloads briefly to reduce duplicate scanner calls
- Suppresses only the specific upstream `Timestamp.utcnow` deprecation warning
- Removes quarantined symbols from broad-discovery normalization and the active universe
- Keeps SPY, QQQ, IWM, DIA, and open-position symbols protected from dynamic quarantine
- Isolates ordinary symbol failures rather than allowing them to open a global circuit

Relevant commits:

- `09ea8716c43df758bdc6f6183ef2369a8a9c56eb` — invalid-symbol quarantine and request hygiene
- `a32da49c0af582d369d2bcad813486d688fc8930` — wrapper-aware provider-health telemetry
- `eb15bd2ab6393e6d06d76a16e641f4fd50d4454f` — protected market data and exact-lifecycle MAE/MFE containment
- `d6d66b425917a6d570d55cd85d7478f86608aa96` — deterministic deferred-startup registration
- `d9a93e9cb63ec3e227e08d7c090ff070c2327fa3` — compact/finalized daily audit and explicit integrity reporting

## Current Effective Participation and Risk Limits

Unless a separately validated controlled-expansion state is active:

- Maximum standard starter positions: `4`
- Maximum standard starter entries per day: `3`
- Risk-on starter entries per cycle: `1`
- Normal position target: approximately `12%–18%` of equity
- Maximum account risk per trade at the configured stop: `2%`
- Starter cash check: at least `35%` cash before another starter
- Practical post-sizing cash reserve: approximately `30%`
- Practical standard deployment ceiling: approximately `70%`
- Absolute daily-loss ceiling: `3%`
- Hard intraday drawdown halt: `2.5%`

The controlled-expansion layer has higher conditional ceilings. Do not treat them as normal allowances or bypass its favorable-regime and safety requirements.

## Machine Learning — Current Role

ML remains shadow recommendation only. It may evaluate candidates and record recommendations and outcomes, but it cannot select entries or exits, size orders, override rules, alter risk, place orders, or obtain live authority.

Executed outcomes receive stronger evidence weight. Counterfactual outcomes remain discounted and do not count toward promotion gates.

Any invalid or unverifiable MAE/MFE feature remains quarantined. No ML authority expansion is permitted without formal evidence and explicit user authorization.

## Remaining Technical Debt and Priority Order

1. Validate at least one newly opened and completed trade through exact symbol, side, entry time, entry price, source observations, exit time, and final MAE/MFE path identity.
2. Verify that every shadow-ML training and promotion surface continues excluding invalid or quarantined path features.
3. Recompute or backfill historical path rows only when authoritative lifecycle data and source bars are available; otherwise preserve quarantine.
4. Confirm the deployed compact `/paper/daily-audit` and full `/paper/daily-audit?full=1` contracts through live workflow evidence.
5. Monitor several ordinary market-open cycles and quantify scanner/provider/runtime duration without forced diagnostic refreshes.
6. Investigate repeated HTTP 401 responses from the custom market-wide momentum query while preserving day-gainer and most-active fallbacks.
7. Continue sector/industry enrichment and quantify classification coverage by cycle.
8. Compare broad-discovered and original-list candidates using only trustworthy outcome labels.
9. Evaluate the profit-giveback guard after more evidence; do not change it from one day of results.
10. Reconcile the optional `/paper/runtime-shadow-capture-status` 404 while preserving in-state runtime-shadow parity.
11. Continue resolving legacy architecture-ownership and typed-configuration findings.
12. Continue accumulating valid ML outcomes without changing authority.

## Proactive Performance-Improvement Directive

At the start of substantive work, inspect fresh live state, the compact and full daily audits, scanner coverage, decision telemetry, execution results, provider health, persistence, ML evidence quality, and technical-debt signals.

Rank proposed changes by expected effect on risk-adjusted expectancy, supporting evidence, downside risk, implementation complexity, and reversibility. Prefer structural improvements over indiscriminately weakening thresholds.

Proactive analysis does not grant trading authority. Behavioral changes must be isolated, tested, reviewed for authority impact, deployed, and verified against live read-only evidence.

## Validation and Deployment State

Validated successful for runtime commit `d9a93e9`:

- Focused compact-audit/integrity tests: `3/3`
- Test workflow configuration parses successfully
- PR merged cleanly with branch ahead of and not behind `main`
- Railway `splendid-creativity / web`: success
- Railway `dazzling-dedication / Trading-bot`: success

Still requiring explicit post-deployment evidence:

- Compact endpoint response type and bounded shape
- Full endpoint response with 13 section objects
- Conclusion count of 11 operational checks
- Continued zero active contaminated features after deployment
- Final custom GitHub `daily-operational-audit` status, if/when surfaced

The separate refactor/governance audit may remain red because of previously documented legacy ownership/configuration findings. Do not misclassify that as a live Railway outage.

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
- Do not equate safe quarantine with completed forward validation

## Next-Session Instruction

Read this document before modifying the project. Start from the latest merged `main` and fresh live state. First verify both daily-audit modes, persistence, cycle completion, scanner boundary, provider health, ML authority, and broad-discovery status. Continue the MAE/MFE effort by collecting trustworthy forward exact-lifecycle evidence, not by loosening strategy controls. Preserve the user's moderate-to-aggressive risk posture while honoring the 3% daily-loss ceiling, 2% per-trade risk ceiling, and rules-gated paper-only architecture.
