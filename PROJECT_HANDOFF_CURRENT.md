# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-06 afternoon CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Runtime code head covered: `f14b25e2b76b21d42007dc60e7ceb232d7e6c126`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway project/service: `splendid-creativity / web`

This is the authoritative handoff. Older `PROJECT_HANDOFF_*` files are historical context unless this document explicitly references them.

## Executive Status

The paper bot remains deployed with persistent Railway state, broad-market momentum discovery, a canonical 110-symbol detailed-scanner boundary, reconciled audit/journal reporting, protected-symbol provider hygiene, exact-lifecycle MAE/MFE containment, and a rules-gated ML counterfactual ledger.

The runtime remains paper-only. The existing rules engine is the sole execution authority. ML remains `shadow_recommendation_only` and cannot place orders, select or override entries/exits, alter sizing, relax hard risk, change thresholds, or obtain live authority.

The MAE/MFE incident is safely contained but not fully closed. Legacy or unverifiable rows remain quarantined and training-ineligible. Completion still requires trustworthy forward evidence from at least one newly opened and completed exact-lifecycle trade.

## Latest Runtime Change

PR `#16`, **Add bootstrap registration heartbeat and provider accounting**, was squash-merged as:

- Runtime commit: `f14b25e2b76b21d42007dc60e7ceb232d7e6c126`
- Bootstrap version: `deferred-wsgi-bootstrap-2026-08-06-v6-registration-heartbeat`
- Data-integrity startup bridge: `data-integrity-startup-bridge-2026-08-06-v2-provider-accounting`
- Provider accounting overlay: `provider-request-accounting-overlay-2026-08-06-v1`

This change is observability-only. It does not change strategy, thresholds, provider request behavior, retries/backoff, sizing, hard-risk controls, order placement, live authority, or ML authority.

Implemented behavior:

- `/bootstrap-status` refreshes every five seconds while synchronous runtime-worker registration is active.
- Bootstrap reports `registration_elapsed_seconds`.
- Bootstrap reports `registration_slow: true` after 60 seconds without misclassifying an active loader as failed.
- Ready bootstrap status retains `registration_duration_seconds`.
- Provider totals now include `classified_terminal_outcomes`, `in_flight_or_unclassified_requests`, and `accounting_complete_at_snapshot`.
- Provider `timeouts` remain a separately reported failure subtype and are not double-counted.
- The GitHub daily-audit workflow directly watches and validates the bootstrap and provider-accounting files.

Both Railway deployment contexts reported success for `f14b25e`:

- `splendid-creativity / web`: success
- `dazzling-dedication / Trading-bot`: success

The custom `daily-operational-audit` push-workflow status had not surfaced through the available connector when this handoff was updated. Do not treat absence of that custom status as a failure; distinguish it from the confirmed Railway deployment statuses.

## Cold-Start Evidence and Interpretation

The first two post-deployment requests to `/paper/daily-audit` returned expected bootstrap `503 Service Unavailable` payloads while the deferred application was still loading:

- First observation: approximately `83.732` seconds elapsed
- Second observation: approximately `96.206` seconds elapsed
- Phase: `runtime_worker_registration`
- `delegate_ready`: `false`
- Loader thread started and alive: `true`
- No startup error was reported

The later `/paper/data-integrity-audit-status` response returned normally with `applied: true` and `overall: pass`. Under the bootstrap contract, non-bootstrap application routes are served only after `runtime_worker_registration.register(...)` returns successfully and the delegate is activated. Therefore the evidence indicates a slow cold start that subsequently completed, not a persistent deployment failure.

The prior bootstrap version updated `elapsed_seconds` dynamically but left `updated_local` unchanged during the long synchronous registration call. The v6 heartbeat corrects that observability gap. It does not shorten startup or reorder runtime composition.

## Latest Data-Integrity Evidence

The post-deployment data-integrity status reported:

- Overall: `pass`
- Active contaminated features: `0`
- Protected benchmark symbols blocked: `0`
- Provider circuit open: `false`
- Active symbol backoffs: `0`
- Invalid or quarantined path rows: `4`
- Valid exact-lifecycle path rows: `0`
- Training-eligible path rows: `0`
- Recomputed rows: `0`
- ML rows enriched: `0`
- ML rows quarantined: `3,825`
- Trade rows enriched: `0`
- Trade rows quarantined: `9`
- Total quarantined feature rows: `3,834`
- Forward validation complete: `false`
- Historical backfill established: `false`

Interpretation:

- The `3,834` quarantined feature rows are historical/shadow records that are now explicitly excluded; they are not active contamination.
- `active_contaminated_feature_count: 0` is the decisive safety metric.
- `valid_path_rows: 0` means MAE/MFE-derived evidence must remain disabled for strategy, risk, stop/target, promotion, and authority decisions.
- Forward validation should occur naturally on a future exact-lifecycle trade; do not manufacture a trade or weaken thresholds to generate evidence.

## Provider Snapshot Accounting

The observed provider snapshot reported:

- Requests: `228`
- Successes: `227`
- Failures: `0`
- Timeouts: `0`
- Empty responses: `0`
- Hygiene blocks: `0`
- Circuit skips: `0`
- Symbol-backoff skips: `0`

One request was not represented by a terminal outcome at that instant. The most likely operational interpretation is a request in flight while the read-only status snapshot was taken, not a silent failure. The provider accounting overlay now reports this explicitly rather than requiring manual subtraction.

A small temporary gap does not change integrity status. A persistent or growing gap across completed cycles should be investigated as unclassified telemetry.

## Canonical Operating Links

- Bootstrap status: `/bootstrap-status`
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

## Daily Audit Contract

Routine operator use should call `/paper/daily-audit`. Detailed diagnosis and automated validation should call `/paper/daily-audit?full=1`.

Required invariants:

- Compact response type: `daily_operational_audit_compact`
- Full response type: `daily_operational_audit`
- Full section-object count: `13`
- Operational checked-section count: `11`
- Integrity section key: `10b_market_data_and_path_integrity`
- Audit route performs no provider fan-out, trading action, repair action, or heavy research
- Audit authority remains reporting-only

The compact payload includes account/equity, runner health, active errors, risk/halt state, scanner signals and blockers, journal/persistence reconciliation, provider/path integrity, and the required next action.

## Latest Account and Risk Baseline

Most recent captured afternoon baseline before the bootstrap follow-up:

- Cash: `$9,964.09`
- Equity: `$9,964.09`
- Open positions: `0`
- Realized today: `-$35.97`
- Realized total: `-$35.92`
- Unrealized P&L: `$0.00`
- Wins/losses: `1 / 4`
- Net daily-loss metric: `0.12%`
- Intraday drawdown: `0.12%`
- Trading halted: `false`
- Self-defense active: `false`

Risk limits remain:

- Soft daily-loss pause: `1.0%`
- Hard realized-loss halt: `2.5%`
- Hard intraday drawdown halt: `2.5%`
- Absolute daily-loss ceiling: `3.0%`
- Maximum account risk per trade at configured stop: `2.0%`

## Scanner and Participation Architecture

Discovery sources include market-wide momentum, day gainers, most-active stocks, current positions, SPY/QQQ/IWM/DIA, and bounded original-watchlist fallback coverage.

Bounds:

- Maximum retained discovery candidates: `160`
- Maximum broad-momentum slots: `80`
- Maximum base/fallback slots: `25`
- Maximum detailed-scanner input: `110`
- Discovery cache: `900` seconds

Canonical scanner chain:

1. Broad-universe boundary
2. Opening-surge participation
3. Breakout participation
4. Market-participation accelerator

The authoritative universe metric is the detailed-scanner boundary, not the temporarily expanded shared `UNIVERSE` between cycles.

Normal participation limits unless controlled expansion is separately validated:

- Maximum standard starter positions: `4`
- Maximum standard starter entries per day: `3`
- Risk-on starter entries per cycle: `1`
- Normal position target: approximately `12%–18%` of equity
- Starter cash check: at least `35%` cash before another starter
- Practical standard deployment ceiling: approximately `70%`

## Machine Learning — Current Role

ML remains shadow recommendation only. Executed outcomes receive stronger evidence weight; counterfactual outcomes remain discounted and do not count toward promotion gates.

Invalid or unverifiable MAE/MFE features remain quarantined. No ML authority expansion is permitted without formal evidence and explicit user authorization.

## Priority Order

1. Verify the deployed bootstrap v6 heartbeat on the next cold start: advancing `updated_local`, increasing `registration_elapsed_seconds`, and final `registration_duration_seconds`.
2. Confirm provider accounting reports the observed one-request gap as `in_flight_or_unclassified_requests: 1`, or zero after the request completes.
3. Validate at least one naturally occurring newly opened and completed trade through exact symbol, side, entry time, entry price, source observations, exit time, and final path identity.
4. Verify every shadow-ML training and promotion surface continues excluding invalid or quarantined path features.
5. Recompute historical path rows only when authoritative lifecycle data and source bars exist; otherwise preserve quarantine.
6. Monitor ordinary market-open cycles and quantify scanner/provider/runtime duration without forced diagnostic refreshes.
7. Investigate repeated HTTP 401 responses from the custom market-wide momentum query while preserving day-gainer and most-active fallbacks.
8. Continue sector/industry enrichment and classification-coverage measurement.
9. Compare broad-discovered and original-list candidates using only trustworthy outcome labels.
10. Evaluate profit-giveback behavior only after more evidence; do not change it from one day of results.
11. Continue resolving legacy architecture-ownership and typed-configuration findings.

## Non-Negotiable Safety Boundaries

- Paper trading only
- Rules engine remains execution authority
- ML remains shadow recommendation only
- No restoration claims for missing historical TSM/HWM state
- No bypass of hard risk, drawdown, daily-entry, spacing, position, sector, bucket, or sizing controls
- Never infer deployment success only from a GitHub commit; verify Railway
- Never infer persistence only from code; verify `/app/data/state.json` and its backup
- Do not weaken thresholds merely to create more trades; diagnose the mechanism first
- Do not train on, promote from, or optimize against telemetry that failed integrity checks
- Do not equate safe quarantine with completed forward validation
- Do not interpret a live bootstrap heartbeat as completed startup; readiness requires `delegate_ready: true`

## Next-Session Instruction

Read this document before modifying the project. Start from the latest merged `main` and fresh live state. Verify bootstrap readiness, both daily-audit modes, persistence, cycle completion, scanner boundary, provider accounting, ML authority, and broad-discovery status. Continue the MAE/MFE effort by collecting trustworthy forward exact-lifecycle evidence, not by loosening strategy controls. Preserve the user's moderate-to-aggressive risk posture while honoring the 3% daily-loss ceiling, 2% per-trade risk ceiling, and rules-gated paper-only architecture.
