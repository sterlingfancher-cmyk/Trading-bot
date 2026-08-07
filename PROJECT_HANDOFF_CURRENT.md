# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-07 morning CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Runtime code head covered: `bbce42192183297b6478d5248c6b21b4b1983b55`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway contexts: `splendid-creativity / web` and `dazzling-dedication / Trading-bot`

This is the authoritative handoff. Older `PROJECT_HANDOFF_*` files are historical context unless this document explicitly references them.

## Executive Status

The paper bot remains deployed with persistent Railway state, broad-market momentum discovery, a canonical 110-symbol detailed-scanner boundary, reconciled audit/journal reporting, protected-symbol provider hygiene, exact-lifecycle MAE/MFE containment, and a rules-gated ML counterfactual ledger.

The runtime remains paper-only. The existing rules engine is the sole execution authority. ML remains `shadow_recommendation_only` and cannot place orders, select or override entries/exits, alter sizing, relax hard risk, change thresholds, or obtain live authority.

The MAE/MFE incident is safely contained but not fully closed. Legacy or unverifiable rows remain quarantined and training-ineligible. Completion still requires trustworthy forward evidence from at least one newly opened and completed exact-lifecycle trade.

The project has entered a stabilization-and-evidence phase. Do not add features merely because they are available. Prefer proving reliability, execution correctness, strategy expectancy, and live-readiness gates.

## Latest Runtime Change

PR `#17`, **Fix daily audit recount and provider denominator reporting**, was squash-merged as:

- Runtime commit: `bbce42192183297b6478d5248c6b21b4b1983b55`
- Response reconciliation: `daily-audit-response-reconciliation-2026-08-06-v1`
- Data-integrity startup bridge: `data-integrity-startup-bridge-2026-08-06-v3-response-reconciliation`
- Provider accounting overlay: `provider-request-accounting-overlay-2026-08-06-v2-denominator-safe`

This change is reporting/observability only. It does not change strategy, thresholds, provider request behavior, retries/backoff, sizing, hard-risk controls, order placement, live authority, or ML authority.

PR #17 corrected two defects exposed by the after-close audit:

1. A later reporting wrapper could recalculate `11_conclusion` from only the original ten sections and omit section `10b_market_data_and_path_integrity` from the count. A final response-boundary reconciliation now guarantees the 11-operational-check contract for compact and full audits.
2. Provider accounting incorrectly mixed pre-provider hygiene/backoff filters into the provider-request denominator. Actual provider outcomes are now separated from symbols filtered before a request is made.

Both Railway deployment contexts reported success for `bbce421`:

- `splendid-creativity / web`: success
- `dazzling-dedication / Trading-bot`: success

Prior important runtime change: PR `#16`, **Add bootstrap registration heartbeat and provider accounting**, merged as `f14b25e2b76b21d42007dc60e7ceb232d7e6c126`. It added the registration heartbeat and the first provider-accounting observability layer.

## Latest After-Close Audit Evidence

The full after-close audit captured on 2026-08-06 reported operational health across the trading runtime:

- Cash: `$9,964.09`
- Equity: `$9,964.09`
- Open positions: `0`
- Realized today: `-$35.97`
- Realized total: `-$35.92`
- Unrealized P&L: `$0.00`
- Wins/losses: `1 / 4`
- Auto-runner enabled: `true`
- Latest after-hours cycle: correctly skipped with `market closed: after_regular_session`
- Active runtime error: `false`
- Recursion error active: `false`
- Trading halted: `false`
- Self-defense active: `false`
- Net daily-loss metric: `0.12%`
- Intraday drawdown: `0.12%`
- Scanner entries: `0`
- Scanner rejected signals observed: `15`
- Top blocker reason coverage: `100%`
- Entry pipeline ownership/stability: pass
- Journal execution rows: `9`
- Runtime execution rows: `9`
- Journal/open-position reconciliation: pass
- Persistent mount detected: `true`
- State file: `/app/data/state.json`
- Backup exists: `true`
- In-memory/on-disk richness: matched
- Runtime shadow parity: `true`
- Provider circuit open: `false`
- Protected symbols blocked: `0`
- Active contaminated MAE/MFE features: `0`

The audit payload still showed `checked_sections: 10` because the reporting defect described above was present in that deployed version. All eleven operational section objects were actually present and passing. PR #17 corrected the response-count defect.

## Latest Data-Integrity / MAE-MFE Evidence

Most recent captured values:

- Invalid or quarantined path rows: `4`
- Valid exact-lifecycle path rows: `0`
- Training-eligible path rows: `0`
- Recomputed rows: `0`
- ML rows enriched: `0`
- ML rows quarantined: `4,710`
- Trade rows enriched: `0`
- Trade rows quarantined: `9`
- Total quarantined feature rows: `4,719`
- Active contaminated feature count: `0`
- Forward validation complete: `false`
- Historical backfill established: `false`

Interpretation:

- Quarantined feature rows are explicitly excluded evidence, not active contamination.
- `active_contaminated_feature_count: 0` is the decisive safety metric.
- `valid_path_rows: 0` means MAE/MFE-derived evidence must remain disabled for strategy, risk, stop/target, promotion, and authority decisions.
- Forward validation should occur naturally on a future exact-lifecycle trade; do not manufacture a trade or weaken thresholds to generate evidence.

## Provider Accounting

The latest after-close snapshot reported:

- Provider requests: `5,081`
- Successes: `5,081`
- Failures: `0`
- Timeouts: `0`
- Empty responses: `0`
- Hygiene-blocked symbols: `3`
- Provider circuit skips: `0`
- Symbol-backoff skips: `0`

Correct interpretation after PR #17:

- Provider terminal outcomes: `5,081`
- Pre-provider filtered symbols: `3`
- In-flight or unclassified provider requests: `0`
- Provider accounting complete at snapshot: `true`

Hygiene and symbol-backoff filters occur before the provider-request denominator and must not be added to terminal provider outcomes. Empty responses and timeouts are failure subtypes and must not be double-counted.

## Morning Operator Observation — 2026-08-07

The user reported seeing substantial green across the board and a majority of ticker symbols positive during the morning session.

Treat this as useful market-context/operator observation only. It is not independently verified performance evidence and must not be used by itself to relax thresholds, alter risk, promote ML authority, or accelerate the live-launch gates. Use completed-cycle and completed-trade telemetry for evidence.

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

## Risk Boundaries

Current operating boundaries remain:

- Soft daily-loss pause: `1.0%`
- Hard realized-loss halt: `2.5%`
- Hard intraday drawdown halt: `2.5%`
- Absolute daily-loss ceiling: `3.0%`
- Maximum account risk per trade at configured stop: `2.0%`
- Standard starter positions: maximum `4`
- Standard starter entries per day: maximum `3`
- Risk-on starter entries per cycle: `1`
- Normal position target: approximately `12%–18%` of equity
- Starter cash check: at least `35%` cash before another starter
- Practical standard deployment ceiling: approximately `70%`

The audit's displayed `net_daily_loss_pct` comes from the runtime's stored day-start equity baseline. Realized-ledger loss safety is calculated separately. Do not assume those two values must always be numerically identical after restart/redeployment/baseline restoration.

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

## Machine Learning — Current Role

ML remains shadow recommendation only. Executed outcomes receive stronger evidence weight; counterfactual outcomes remain discounted and do not count toward promotion gates.

Invalid or unverifiable MAE/MFE features remain quarantined. No ML authority expansion is permitted without formal evidence and explicit user authorization.

LONA may be used for independent strategy development, backtesting, robustness testing, and comparison work. Codex/GitHub tooling may be used for code inspection, regression review, implementation, debugging, and deployment work. Neither changes the execution-authority boundary: the rules engine remains the only execution authority unless the user explicitly approves a later promotion after evidence gates are satisfied.

## Live-Readiness Roadmap and Goals

The dates below are targets, not automatic promotion dates. Promotion is evidence-gated. If the evidence is not sufficient, remain at the current stage regardless of calendar date.

### Goal 1 — Paper Stability

Target window: **2026-08-07 through approximately 2026-08-21**.

Desired evidence:

- Approximately `7–10` consecutive trading days with clean operational behavior.
- Daily audit consistently passes with zero unexplained fail states.
- No persistence or redeployment surprises.
- No stale, overlapping, or orphaned cycles.
- Provider health remains stable and denominator accounting reconciles.
- Journal and execution records reconcile daily.
- Risk controls and after-hours skip behavior remain correct.
- Scanner participation is healthy without weakening thresholds merely to create trades.
- No new architecture/runtime defects requiring trading-logic intervention.

### Goal 2 — Validate Actual Trade Behavior

Target window: **weeks 2–4**, approximately mid-to-late August 2026.

Collect enough naturally occurring completed trades under the current architecture to validate:

- Entry execution and lifecycle identity.
- Stop behavior.
- Profit taking and profit protection.
- Rotation and exit behavior.
- Position sizing and cash deployment.
- Daily loss / drawdown controls.
- Scanner → decision → execution consistency.
- Exact-lifecycle MAE/MFE capture.
- Paper slippage assumptions and any fill-model limitations.

MAE/MFE forward validation is an explicit gate. Do not rely on MAE/MFE optimization inputs until at least one valid new exact-lifecycle row exists and the enrichment remains contamination-free.

Use LONA during this phase for independent backtesting/robustness challenges rather than relying only on the bot's own historical tests.

### Goal 3 — Live-Readiness Simulation

Target window: **weeks 3–5**, approximately late August to early September 2026.

Operate the paper account as if it were live:

- Do not manually rescue trades merely because the outcome is uncomfortable.
- Do not change thresholds because of one poor or quiet day.
- Do not force trades to create evidence.
- Compare expected order → generated order → simulated fill → resulting position → exit → journal.
- Audit restart/redeployment behavior and broker-state assumptions.
- Use Codex/GitHub review for regression and execution-path inspection as needed.

### Goal 4 — Controlled Micro-Live Pilot

Earliest target: **September 2026**, approximately 4–6 weeks from 2026-08-07 if all prior gates pass.

This stage is intentionally small and should use a more restrictive initial live envelope than the normal paper envelope. Its purpose is execution validation, not maximizing profit.

Required focus:

- Real fills and bid/ask spread.
- Partial fills.
- Broker/API latency.
- Rejected/cancelled orders.
- Position and buying-power synchronization.
- Order-state race conditions.
- Real slippage versus modeled assumptions.
- Network/provider interruptions.
- Market-open execution behavior.
- Hard-risk enforcement under real broker state.

Do not fund or size the pilot as if full strategy expectancy has already been proven.

### Goal 5 — Normal Live Operation

Target: **October 2026 or later**, only after approximately `15–25` clean live trading days and adequate trade evidence.

Promotion criteria should include:

- Credible positive expectancy or other sufficiently strong risk-adjusted evidence.
- Drawdowns behaving within modeled limits.
- Real slippage reasonably consistent with assumptions.
- No unexplained broker/account reconciliation events.
- No critical execution failures.
- No risk-control bypass.
- Enough completed trades to distinguish strategy behavior from short-run randomness.
- Continued rules-engine execution authority unless a separate ML promotion is explicitly approved.

## Promotion Principle

The working launch targets are:

- **September 2026:** controlled micro-live candidate.
- **October 2026:** potential normal live-operation candidate.

These are not deadlines. The system must earn promotion through evidence.

Primary operating principle between now and live launch:

> Stop adding features unless they solve a demonstrated problem. Accumulate clean evidence, challenge assumptions, and promote only when reliability and expectancy justify it.

## Priority Order

1. Verify PR #17 audit reconciliation in live compact/full payloads: `checked_sections: 11` and provider denominator-safe accounting.
2. Continue ordinary paper-market observation without forcing trades or loosening thresholds.
3. Capture at least one naturally occurring newly opened and completed exact-lifecycle trade.
4. Confirm that trade produces a valid path row and training-eligible enrichment without active contamination.
5. Verify every shadow-ML training and promotion surface continues excluding invalid or quarantined path features.
6. Monitor `7–10` consecutive trading days for paper-stability evidence: audits, persistence, cycles, provider accounting, reconciliation, and risk controls.
7. Build a completed-trade evidence set for entry/exit behavior, stop/profit handling, sizing, slippage assumptions, and scanner-to-execution consistency.
8. Use LONA for independent robustness/backtest challenges where it materially improves evidence quality.
9. Use Codex/GitHub tooling for regression review, code inspection, debugging, and deployment when needed.
10. Investigate repeated HTTP 401 responses from the custom market-wide momentum query while preserving day-gainer and most-active fallbacks.
11. Continue sector/industry enrichment and classification-coverage measurement only when it does not distract from stabilization evidence.
12. Evaluate strategy changes only from trustworthy completed outcomes, not from one green or red session.
13. Begin live-readiness simulation only after paper stability is demonstrated.
14. Consider micro-live only after all prior gates pass; consider normal live operation only after clean micro-live evidence.

## Non-Negotiable Safety Boundaries

- Paper trading only until the live-readiness promotion gates are explicitly approved.
- Rules engine remains execution authority.
- ML remains shadow recommendation only.
- No restoration claims for missing historical TSM/HWM state.
- No bypass of hard risk, drawdown, daily-entry, spacing, position, sector, bucket, or sizing controls.
- Never infer deployment success only from a GitHub commit; verify Railway.
- Never infer persistence only from code; verify `/app/data/state.json` and its backup.
- Do not weaken thresholds merely to create more trades; diagnose the mechanism first.
- Do not train on, promote from, or optimize against telemetry that failed integrity checks.
- Do not equate safe quarantine with completed forward validation.
- Do not interpret a live bootstrap heartbeat as completed startup; readiness requires `delegate_ready: true`.
- Do not promote to live simply because a target date has arrived.

## Next-Session Instruction

Read this document before modifying the project. Start from the latest merged `main` and fresh live state. Verify bootstrap readiness, both daily-audit modes, persistence, cycle completion, scanner boundary, provider accounting, ML authority, and broad-discovery status. Continue the MAE/MFE effort by collecting trustworthy forward exact-lifecycle evidence, not by loosening strategy controls. Treat the project as being in stabilization/evidence mode. Preserve the user's moderate-to-aggressive risk posture while honoring the 3% daily-loss ceiling, 2% per-trade risk ceiling, and rules-gated paper-only architecture until the explicit live-readiness gates are earned and approved.
