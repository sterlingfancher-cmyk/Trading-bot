# Automated Trading Project Handoff — Updated July 24, 2026

## Engineering Constitution

1. Reliability before performance.
2. Evidence before modification.
3. Deterministic behavior before adaptive behavior.
4. Diagnostics before optimization.
5. Backtests do not replace live paper validation.
6. New capability must improve measurable performance without weakening risk controls.
7. Machine learning remains advisory until sufficient execution history, observed outcomes, out-of-sample evidence, and regime stability justify greater influence.
8. Significant changes must be traceable, reversible, and validated before becoming the new baseline.
9. No filter, threshold, or risk control may be relaxed solely because a stock finished strongly.
10. State must never be automatically restored, merged, or rewritten until the precise source of divergence is proven.

## Standing Rule

Every code or configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Always Resume Here

- Highest-priority unfinished milestone: validate merge commit `9998c597ef91b5d6edce47cdf481efcb6ac4cc90` on Railway.
- First endpoint: `https://trading-bot-clean.up.railway.app/paper/self-check`.
- Next evidence required: confirm the deployed compact response exposes `missing_reason_symbols`, `missing_reason_sample`, and `missing_reason_trace_version`.
- Next likely code change: repair only the diagnostic producer contract identified by `missing_reason_sample`; do not infer or synthesize a blocker reason.
- Parallel evidence task: capture at least two deployment-local state-provenance observations around a normal paper cycle.
- Advancement condition: compact validation passes, blocker attribution reaches 100%, and append-only counters remain consistent across observations without unexplained state-source changes.
- Escalation condition: use `/paper/full-self-check` only after a failed compact check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Executive Status Dashboard

| Item | Current status |
|---|---|
| Project phase | Reliability, observability, and ML data-readiness validation |
| Overall health | Yellow — last compact production check passed; newly merged diagnostics still require Railway validation |
| Repository | `sterlingfancher-cmyk/Trading-bot` |
| Default branch | `main` |
| Latest merged change | PR #6, merge commit `9998c597ef91b5d6edce47cdf481efcb6ac4cc90` |
| Railway base URL | `https://trading-bot-clean.up.railway.app` |
| Operating mode | Paper only |
| Live trade authority | None |
| ML authority | Advisory only; no execution or live authority |
| Stronger-authority benchmark | At least 150 execution rows and 100 observed outcomes, plus satisfactory validation evidence |
| Last known compact validation | July 24, 2026 at `15:19:30`; passed before PR #6 redeploy |
| Active issue | One blocker row lacks terminal reason detail |
| State-consistency issue | Prior backward movement in append-only counters requires deployment-local provenance observation |
| Immediate milestone | Validate PR #6 deployment, identify missing-reason producer, and verify provenance stability |

## Autonomous Engineering Workflow

Continue sequential diagnostic, observability, reliability, documentation, and advisory-only milestones without waiting for approval after each successful validation. Pause for approval before changing executable-universe membership, scanner or signal results, entry/exit logic, thresholds, risk controls, position sizing, order placement, ML decision authority, live-trading authority, or a material architecture decision with multiple reasonable behavioral outcomes.

## Autonomous Operations Manual

Whenever work resumes:

1. Read this handoff before inspecting or modifying code.
2. Start from **Always Resume Here**, not from an assumed project state.
3. Confirm the deployed commit and runtime evidence before diagnosing source code.
4. Inspect existing diagnostics and producer contracts before adding another overlay.
5. Form an evidence-backed hypothesis and make the smallest safe change that resolves or isolates the defect.
6. Preserve the Safety and Authority Boundary unless the user explicitly authorizes behavioral change.
7. Validate in the documented endpoint order.
8. Treat compact validation as the routine gate; reserve full diagnostics for escalation conditions.
9. Update this handoff in the same work session with files, versions, commits, routes, evidence, safety impact, and next action.
10. Advance automatically to the next advisory-only milestone after successful validation.
11. Stop and request approval before any strategy, risk, execution, universe, ML-authority, live-authority, or material architectural change.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `/paper/self-check`
- Full diagnostics: `/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Stronger-authority benchmark: 150 execution rows and 100 observed outcomes, subject to the additional ML validation gates below

## Milestone Roadmap

| Milestone | Status | Evidence / exit condition |
|---|---|---|
| Core paper-trading infrastructure | Complete | Deployed paper service and persistent operating history |
| Runtime market-data resilience | Complete | `market-data-resilience-2026-07-22-v1`; provider-health route available |
| Recursion-safe entry composition | Complete | Repeated compact checks report stable composition |
| Decision/blocker cycle alignment | Complete | Same-cycle comparison true and count difference zero |
| State provenance monitor v2 | Implemented; deployment validation pending | Merge commit `9998c597...`; require multiple normal-cycle observations |
| Missing blocker-reason trace v1 | Implemented; deployment validation pending | Require exact producer sample, then 100% reason attribution |
| Diagnostic producer-contract repair | In progress | Repair only the source identified by trace evidence |
| State persistence consistency | In progress | Append-only counters stable or divergence source proven |
| ML data collection and lineage | In progress | Execution and decision records remain attributable, durable, and internally consistent |
| ML dataset readiness gate | Planned | Sufficient rows/outcomes, complete labels, stable feature contracts, leakage review |
| Offline model training pipeline | Planned | Reproducible train/validation/test process with versioned data and models |
| Out-of-sample and walk-forward testing | Planned | Improvement survives unseen data and multiple market regimes |
| Shadow advisory inference | Planned | Model runs beside deterministic engine without affecting decisions |
| Controlled ML influence | Future; approval required | Demonstrated incremental value and bounded deterministic safeguards |
| Live-trading readiness | Future; approval required | Operational, risk, execution, and governance gates all satisfied |

## Current Sprint

### Objective

Finish deployment validation for PR #6, close the remaining blocker-attribution gap, and establish trustworthy state and ML-data provenance.

### Work items

1. Validate `/paper/self-check` after Railway deploys merge commit `9998c597...`.
2. Confirm state-provenance v2 and missing-reason trace v1 are registered and returning expected fields.
3. Capture `missing_reason_sample` and identify the exact diagnostic producer contract.
4. Repair only that producer contract, with no scanner-result or trading-behavior change.
5. Revalidate until blocker reason coverage is 100%.
6. Capture at least two state-provenance observations around a normal paper cycle.
7. If an append-only counter regresses, compare revision, path, file hash, source hint, persistence mode, transaction status, and backup event before considering any restoration behavior.
8. Confirm the retained data is suitable for the next ML data-readiness review.

### Definition of done

- Railway is running the intended merged commit.
- Compact self-check passes without missing critical fields, runtime errors, or unexpected warnings.
- `missing_reason_rows` equals zero and reason coverage is 100%.
- No fabricated blocker reason is introduced.
- State revision, execution rows, wins, and losses behave consistently across observed cycles, or any divergence is precisely attributed.
- ML remains advisory-only with all authority fields false.
- This handoff contains final validation evidence and the next active milestone.

## Machine Learning Roadmap

### ML-0 — Governance and authority boundary

**Status:** Active and enforced.

- Deterministic strategy remains the source of truth.
- ML may score, rank, explain, or advise, but may not place orders or override deterministic risk controls.
- No increase in ML authority occurs automatically.

**Exit gate:** None; this remains the permanent control framework.

### ML-1 — Data integrity, lineage, and labeling

**Status:** In progress.

Required records include:

- every evaluated candidate and decision cycle;
- entries taken and entries blocked;
- terminal blocker reason and producer source;
- market regime and market-data provenance;
- feature values and feature-contract version;
- entry, exit, holding period, exit reason, realized outcome, and risk context;
- enough identifiers to join decisions, executions, positions, and outcomes without ambiguity.

Current dependencies:

- close the final missing blocker-reason row;
- prove state and execution-history persistence consistency;
- preserve cycle alignment and source attribution.

**Exit gate:** Dataset is internally consistent, attributable, durable, and free of known critical labeling gaps.

### ML-2 — Dataset readiness and feature governance

**Status:** Planned.

- Establish a versioned training-table contract.
- Separate features available at decision time from future outcome labels.
- Review for target leakage, survivorship bias, duplicate observations, stale prices, and regime imbalance.
- Define train, validation, test, and walk-forward partitions.
- Document feature definitions, missing-value behavior, scaling, and categorical handling.

**Minimum maturity benchmark:** At least 150 execution rows and 100 observed outcomes. This is necessary but not sufficient; label completeness, regime diversity, and out-of-sample integrity must also pass.

### ML-3 — Reproducible offline training pipeline

**Status:** Planned.

- Version dataset snapshots, feature contracts, hyperparameters, model artifacts, and evaluation reports.
- Establish deterministic seeds and reproducible training runs.
- Begin with interpretable baselines before complex models.
- Compare against deterministic strategy baselines and simple heuristics.

**Exit gate:** Repeated training runs reproduce materially equivalent results and outperform the relevant baseline on held-out data without unacceptable risk degradation.

### ML-4 — Out-of-sample, walk-forward, and regime validation

**Status:** Planned.

Evaluate:

- precision and recall for trade-quality classification;
- calibration of confidence scores;
- expectancy, drawdown, Sharpe-like risk-adjusted metrics, and tail behavior;
- stability across bullish, bearish, sideways, high-volatility, and low-liquidity conditions;
- sensitivity to data gaps and provider degradation;
- turnover and concentration impacts.

**Exit gate:** Incremental value persists across unseen periods and multiple regimes, not merely in aggregate backtests.

### ML-5 — Shadow advisory inference

**Status:** Planned.

- Run model inference alongside the deterministic engine.
- Record model recommendations without changing entries, exits, sizing, or orders.
- Compare counterfactual ML recommendations with realized deterministic outcomes.
- Monitor drift, calibration, missing features, latency, and model/data-version mismatches.

**Exit gate:** Sustained paper evidence shows stable, explainable incremental value with no operational reliability degradation.

### ML-6 — Controlled production influence

**Status:** Future and requires explicit approval.

Potential bounded uses, introduced one at a time:

- ranking otherwise eligible candidates;
- confidence weighting inside predetermined limits;
- recommending parameter variants for offline evaluation;
- allocating a small experimental paper-only sleeve.

Hard risk controls, order limits, and capital protections remain deterministic.

**Exit gate:** Predefined statistical, risk, operational, and rollback criteria are satisfied and the user explicitly authorizes the authority change.

### ML-7 — Autonomous optimization research

**Status:** Future and requires explicit approval.

- Candidate-model generation and challenger evaluation;
- controlled champion/challenger promotion;
- drift-triggered retraining proposals;
- portfolio-level and cross-asset research;
- ensemble or reinforcement-learning research only after simpler methods are exhausted and governance is mature.

No autonomous model promotion to trading authority is permitted without explicit approval and a documented rollback path.

## July 23 Baselines

The July 23 morning compact self-check passed with equity `10970.12`, realized total `970.14`, 88 execution rows, 36 wins, 18 losses, zero open positions, stable recursion-safe entry composition, no current pipeline error, and 54 matching decision/blocker signals.

The afternoon compact self-check generated at `2026-07-23 18:30:47` also passed, with matching same-cycle decision and blocker counts, but cumulative append-only counters moved backward:

- execution rows: `88 -> 83`
- wins: `36 -> 34`
- losses: `18 -> 17`

Net realized P&L also changed, but it is contextual rather than monotonic because legitimate losing exits can reduce it.

## July 24 Morning Validation

The compact self-check generated at `2026-07-24 15:19:30` passed:

- equity: `10954.26`
- cash: `10954.26`
- open positions: `0`
- realized today: `100.25`
- realized total: `954.28`
- execution rows: `85`
- wins/losses: `35 / 18`
- entry pipeline stable and recursion-safe
- no required-path failures or warnings
- decision/blocker cycle ID: `cycle-20260724T151539135164Z-93656e7c`
- same-cycle comparison: `true`
- count difference: `0`
- source mismatch: `false`
- blocker reason coverage: `96.55%`
- missing reason rows: `1`
- ML remains advisory-only with no live authority

The compact test passed, so `/paper/full-self-check` was not warranted.

## Runtime Reliability v3

Version: `market-data-resilience-2026-07-22-v1`

Route: `/paper/provider-health-status`

The guard bounds yfinance requests, records per-symbol latency/outcomes, opens a short circuit after repeated failures, and preserves the legacy unavailable-data contract. It does not alter strategy, thresholds, sizing, risk, orders, executable universe, ML authority, or live authority.

## Cycle Alignment v2

Version: `cycle-alignment-overlay-2026-07-23-v1`

Route: `/paper/cycle-alignment-status`

Decision and blocker producers report the same cycle, and same-cycle count comparison is active.

## State Provenance and Monotonicity Monitor v2

Version: `state-provenance-monitor-2026-07-23-v2`

Route: `/paper/state-provenance-status`

The v2 monitor:

- wraps `load_state` passively and returns the original state unchanged;
- treats only state revision, execution rows, wins, and losses as monotonic counters;
- records realized total, equity, and position count as context-only metrics;
- reports deltas from the previous observation;
- reports state-file hash and path changes between observations;
- serializes sidecar read/compute/write operations under a re-entrant lock;
- uses process- and thread-specific temporary files for atomic sidecar replacement;
- exposes sidecar persistence failures as warnings;
- maintains persistent high-water marks in a separate diagnostic sidecar;
- never restores, overwrites, merges, or modifies trading state.

The sidecar file remains `state_provenance_status.json` in the active state directory. It is diagnostic only and is not used as a trading-state source.

## Missing Blocker-Reason Trace v1

Version: `missing-reason-trace-2026-07-24-v1`

Route: `/paper/missing-reason-trace-status`

The trace overlay addresses the remaining single missing blocker-reason row without fabricating a reason. It:

- reads the existing blocked-entry reason audit;
- exposes a bounded sample containing symbol, source, source key, placeholder, and category;
- adds `missing_reason_symbols`, `missing_reason_sample`, and `missing_reason_trace_version` to the compact scanner section;
- identifies which producer contract omitted terminal reason detail;
- does not alter scanner results, blocker decisions, thresholds, filters, risk, sizing, orders, executable universe, ML authority, or live authority.

The next routine compact test should identify the exact source of the remaining placeholder. Repair the producer contract only after that evidence is visible; do not infer or synthesize a trading reason.

## Safety and Authority Boundary

Current work preserves:

- no live authority;
- no ML execution authority;
- no order placement;
- no threshold changes;
- no sizing or risk-control changes;
- no executable-universe mutation;
- no scanner-result modification;
- no automatic state restoration;
- no mutation of account history or current positions;
- no fabricated blocker attribution.

## Validation Status

- PR #6 merged into `main` on July 24, 2026.
- Merge commit: `9998c597ef91b5d6edce47cdf481efcb6ac4cc90`.
- Pre-merge morning deployed `/paper/self-check`: passed.
- `/paper/full-self-check`: not used because the compact check passed without missing critical fields, required-path failures, runtime errors, or warnings.
- Source-level safety review: trace overlay is read-only and bounded.
- Deployment validation for merge commit `9998c597...` remains pending Railway redeploy confirmation.

## Validation After Merge and Railway Redeploy

Run in this order:

1. `https://trading-bot-clean.up.railway.app/paper/self-check`
2. `https://trading-bot-clean.up.railway.app/paper/state-provenance-status`
3. `https://trading-bot-clean.up.railway.app/paper/missing-reason-trace-status`
4. `https://trading-bot-clean.up.railway.app/paper/state-transaction-status`
5. `https://trading-bot-clean.up.railway.app/paper/cycle-alignment-status`
6. `https://trading-bot-clean.up.railway.app/paper/provider-health-status`

Expected compact scanner fields:

- `missing_reason_rows`
- `missing_reason_symbols`
- `missing_reason_sample`
- `missing_reason_trace_version: missing-reason-trace-2026-07-24-v1`

Expected provenance fields:

- `version: state-provenance-monitor-2026-07-23-v2`
- `current.metrics.state_revision`
- `current.metrics.execution_rows`
- `current.metrics.wins_total`
- `current.metrics.losses_total`
- `current.metrics.realized_total`
- `current.metric_deltas_from_previous`
- `current.state_file.path`
- `current.state_file.sha256_prefix`
- `current.state_file_identity_changed`
- `current.state_file_path_changed`
- `current.source_hint.source`
- `current.persistence_mode`
- `high_water_marks`
- `monotonic_fields`
- `context_only_fields`
- `sidecar_persistence.ok`
- `regression_detected`
- `regressions`
- all authority fields false

Use `/paper/full-self-check` only for a failed routine check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Engineering Decision Log

### 2026-07-23 — Cycle alignment over cross-cycle comparison

Decision: compare decision and blocker diagnostics only when they share the same cycle identifier.

Reason: cross-cycle counts can differ legitimately and should not be treated as pipeline divergence.

### 2026-07-23 — Separate monotonic counters from contextual metrics

Decision: monitor state revision, execution rows, wins, and losses as append-only counters; treat realized P&L, equity, and open-position count as contextual.

Reason: legitimate losses and market movement can reduce contextual metrics without indicating persistence regression.

### 2026-07-24 — Trace missing blocker attribution without fabrication

Decision: expose the exact symbol, source, source key, category, and placeholder for missing-reason rows rather than synthesizing a reason.

Reason: producer-contract repair must be based on evidence and must not modify scanner decisions.

### 2026-07-24 — Promote handoff to operating manual

Decision: maintain an executive dashboard, Always Resume Here section, milestone roadmap, active sprint, ML roadmap, autonomous operations manual, decision log, and prioritized backlog in this file.

Reason: the project now requires durable operating context, explicit authority boundaries, and a resumable sequence of validated milestones.

## Technical Debt and Enhancement Backlog

### Active / highest priority

- Validate merge commit `9998c597...` on Railway.
- Eliminate the final missing blocker-reason row through producer-contract repair.
- Collect multiple state-provenance observations and resolve any source divergence.
- Confirm the decision/execution/outcome records meet ML-1 lineage requirements.

### Next

- Formalize the versioned ML training-table contract.
- Add dataset-readiness diagnostics for missing labels, duplicate records, join failures, feature availability, and regime distribution.
- Define offline baseline models and evaluation metrics.
- Establish reproducible train/validation/test and walk-forward partitions.

### Later; behavior-neutral unless separately approved

- Model and data drift monitoring.
- Champion/challenger reporting.
- Counterfactual shadow-performance reporting.
- Additional operational dashboards and documentation automation.

### Future; explicit approval required

- Changes to scanner thresholds, entries, exits, risk, sizing, executable universe, or order behavior.
- ML ranking or confidence influence over eligible trades.
- Experimental capital allocation controlled by ML.
- Crypto-engine expansion or cross-asset portfolio optimization.
- Any live-trading authority.

## Files and Commits

- `state_provenance_monitor.py`
  - v2 branch commit: `9ce6ddc4e03c38a7c9c4f5e103c2fbbad7f0892b`
- `missing_reason_trace_overlay.py`
  - initial trace overlay: `f42f4c985a7f1a7695c6cafdc46584ab379a63d8`
- `usercustomize.py`
  - missing-reason trace registration: `e0cbdd54775e2e6f17ced686b4e31e3f619d159f`
- PR #6
  - merged commit: `9998c597ef91b5d6edce47cdf481efcb6ac4cc90`
- `PROJECT_HANDOFF.md`
  - expanded into the project operating manual in the current documentation update.

## Next Action

Validate the Railway deployment beginning with `/paper/self-check`. Continue sequentially through the current sprint after successful compact validation.