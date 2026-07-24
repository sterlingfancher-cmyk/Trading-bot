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

- Highest-priority unfinished milestone: validate bounded run-cycle guard commit `d1915e5a79282d0f6ccd541c6024421cf8ad86cd` on Railway.
- First endpoint: `https://trading-bot-clean.up.railway.app/paper/self-check`.
- Then inspect: `https://trading-bot-clean.up.railway.app/paper/run-report-guard-status`.
- Manual-cycle validation: invoke `/paper/run` once only when no other cycle is expected; confirm it either completes normally or returns `status: cycle_busy` promptly instead of reaching Gunicorn timeout.
- Next diagnostic evidence: confirm compact output exposes `missing_reason_symbols`, `missing_reason_sample`, and `missing_reason_trace_version`.
- Next likely code change after validation: repair only the diagnostic producer contract identified by `missing_reason_sample`; do not infer or synthesize a blocker reason.
- Parallel evidence task: capture at least two deployment-local state-provenance observations around a normal paper cycle.
- Advancement condition: compact validation passes, manual run no longer hangs on guard contention, blocker attribution reaches 100%, and append-only counters remain consistent without unexplained source changes.
- Escalation condition: use `/paper/full-self-check` only after a failed compact check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Executive Status Dashboard

| Item | Current status |
|---|---|
| Project phase | Reliability, observability, and ML data-readiness validation |
| Overall health | Yellow — deployment boots, but `/paper/run` experienced a guard-lock worker timeout; bounded recovery is committed and awaiting Railway validation |
| Repository | `sterlingfancher-cmyk/Trading-bot` |
| Default branch | `main` |
| Latest reliability commit | `d1915e5a79282d0f6ccd541c6024421cf8ad86cd` |
| Prior merged diagnostics | PR #6, merge commit `9998c597ef91b5d6edce47cdf481efcb6ac4cc90` |
| Railway base URL | `https://trading-bot-clean.up.railway.app` |
| Operating mode | Paper only |
| Live trade authority | None |
| ML authority | Advisory only; no execution or live authority |
| Stronger-authority benchmark | At least 150 execution rows and 100 observed outcomes, plus satisfactory validation evidence |
| Active reliability issue | Concurrent/background `run_cycle` could hold the report guard while manual `/paper/run` waited until Gunicorn killed the sync worker |
| Active data issue | One blocker row lacks terminal reason detail |
| State-consistency issue | Prior backward movement in append-only counters requires deployment-local provenance observation |
| Immediate milestone | Validate bounded guard behavior, then continue missing-reason and provenance work |

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
- Run guard status: `/paper/run-report-guard-status`
- State provenance: `/paper/state-provenance-status`
- Missing-reason trace: `/paper/missing-reason-trace-status`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Stronger-authority benchmark: 150 execution rows and 100 observed outcomes, subject to the ML validation gates below

## July 24 Runtime Incident — Manual Run Worker Timeout

Railway booted successfully at `2026-07-24 15:59:23 +0000` with Gunicorn 26.0.0, one sync worker, and the persistent volume mounted. At `2026-07-24 17:50:32 +0000`, request `GET /paper/run` exceeded the Gunicorn worker timeout. The traceback ended while `run_report_guard.wrapped_run_cycle` was waiting at `with _LOCK`.

### Root-cause assessment

`run_report_guard.py` used a process-wide re-entrant lock around the entire `run_cycle` call while temporarily replacing `store_compiled_report`. A background or concurrent cycle could therefore hold the lock while the manual request waited without a bound. Because Gunicorn was using one sync worker, the waiting HTTP request eventually triggered `WORKER TIMEOUT`, `SystemExit`, and worker replacement.

### Reliability fix

Version: `run-report-guard-2026-07-24-v2`

Commit: `d1915e5a79282d0f6ccd541c6024421cf8ad86cd`

The guard now:

- preserves one-cycle-at-a-time serialization for the global report-store substitution;
- attempts lock acquisition for a bounded period, default `2.0` seconds;
- clamps configurable `RUN_CYCLE_GUARD_LOCK_TIMEOUT_SECONDS` between `0.1` and `10.0` seconds;
- returns an explicit `status: cycle_busy`, `retryable: true` payload when another cycle owns the guard;
- confirms the rejected request did not execute a cycle or place orders;
- exposes lock timeout and last status on `/paper/run-report-guard-status`;
- preserves deferred inline-report behavior for a successfully acquired cycle.

### Safety impact

No scanner results, signals, entries, exits, thresholds, risk controls, sizing, orders, executable universe, state payload, ML authority, or live authority were changed. The only behavioral difference is that a concurrent manual invocation fails fast and safely instead of occupying the HTTP worker until forced termination.

## Milestone Roadmap

| Milestone | Status | Evidence / exit condition |
|---|---|---|
| Core paper-trading infrastructure | Complete | Deployed paper service and persistent operating history |
| Runtime market-data resilience | Complete | `market-data-resilience-2026-07-22-v1`; provider-health route available |
| Recursion-safe entry composition | Complete | Repeated compact checks report stable composition |
| Decision/blocker cycle alignment | Complete | Same-cycle comparison true and count difference zero |
| Bounded run-cycle guard v2 | Implemented; deployment validation pending | Manual run completes or returns `cycle_busy` promptly; no Gunicorn timeout |
| State provenance monitor v2 | Implemented; deployment validation pending | Require multiple normal-cycle observations |
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

Validate the bounded run-cycle recovery, complete PR #6 deployment diagnostics, close the remaining blocker-attribution gap, and establish trustworthy state and ML-data provenance.

### Work items

1. Confirm Railway deploys commit `d1915e5a79282d0f6ccd541c6024421cf8ad86cd`.
2. Validate `/paper/self-check`.
3. Validate `/paper/run-report-guard-status` reports version `run-report-guard-2026-07-24-v2` and bounded lock timeout.
4. Confirm a manual `/paper/run` does not hang; concurrent contention must return `cycle_busy` promptly.
5. Confirm state-provenance v2 and missing-reason trace v1 return expected fields.
6. Capture `missing_reason_sample` and identify the exact diagnostic producer contract.
7. Repair only that producer contract, with no scanner-result or trading-behavior change.
8. Revalidate until blocker reason coverage is 100%.
9. Capture at least two state-provenance observations around a normal paper cycle.
10. If an append-only counter regresses, compare revision, path, file hash, source hint, persistence mode, transaction status, and backup event before considering restoration.
11. Confirm retained records are suitable for the next ML data-readiness review.

### Definition of done

- Railway is running the intended latest commit.
- Compact self-check passes without missing critical fields, runtime errors, or unexpected warnings.
- Manual `/paper/run` cannot wait indefinitely on the report guard.
- `missing_reason_rows` equals zero and reason coverage is 100%.
- No fabricated blocker reason is introduced.
- State revision, execution rows, wins, and losses behave consistently across observed cycles, or divergence is precisely attributed.
- ML remains advisory-only with all authority fields false.
- This handoff contains final validation evidence and the next active milestone.

## Machine Learning Roadmap

### ML-0 — Governance and authority boundary

**Status:** Active and enforced.

- Deterministic strategy remains the source of truth.
- ML may score, rank, explain, or advise, but may not place orders or override deterministic risk controls.
- No increase in ML authority occurs automatically.

### ML-1 — Data integrity, lineage, and labeling

**Status:** In progress.

Required records include every evaluated candidate and cycle; entries taken and blocked; terminal blocker reason and producer; market regime and data provenance; feature values and contract version; entry, exit, holding period, exit reason, realized outcome, and risk context; and identifiers joining decisions, executions, positions, and outcomes.

Current dependencies:

- close the final missing blocker-reason row;
- prove state and execution-history persistence consistency;
- preserve cycle alignment and source attribution;
- ensure cycle concurrency and request timeouts do not corrupt or ambiguously duplicate records.

**Exit gate:** Dataset is internally consistent, attributable, durable, and free of known critical labeling gaps.

### ML-2 — Dataset readiness and feature governance

**Status:** Planned.

- Establish a versioned training-table contract.
- Separate decision-time features from future labels.
- Review target leakage, survivorship bias, duplicates, stale prices, and regime imbalance.
- Define train, validation, test, and walk-forward partitions.
- Document feature definitions and missing-value handling.

**Minimum maturity benchmark:** At least 150 execution rows and 100 observed outcomes. This is necessary but not sufficient.

### ML-3 — Reproducible offline training pipeline

**Status:** Planned.

Version dataset snapshots, feature contracts, hyperparameters, model artifacts, and reports; establish deterministic seeds; begin with interpretable baselines; compare against deterministic strategy and simple heuristics.

### ML-4 — Out-of-sample, walk-forward, and regime validation

**Status:** Planned.

Evaluate classification quality, calibration, expectancy, drawdown, risk-adjusted performance, tail behavior, regime stability, provider degradation sensitivity, turnover, and concentration.

### ML-5 — Shadow advisory inference

**Status:** Planned.

Run inference beside the deterministic engine, record recommendations without influencing trades, compare counterfactual recommendations with outcomes, and monitor drift, latency, missing features, and model/data-version mismatches.

### ML-6 — Controlled production influence

**Status:** Future and requires explicit approval.

Potential bounded uses include ranking otherwise eligible candidates, limited confidence weighting, offline parameter recommendations, or a small experimental paper-only sleeve. Hard risk controls remain deterministic.

### ML-7 — Autonomous optimization research

**Status:** Future and requires explicit approval.

Candidate-model generation, champion/challenger evaluation, drift-triggered retraining proposals, portfolio research, and ensemble or reinforcement-learning research only after simpler methods and governance mature. No autonomous promotion to trading authority is permitted.

## Safety and Authority Boundary

Current work preserves:

- no live authority;
- no ML execution authority;
- no unauthorized order placement;
- no threshold changes;
- no sizing or risk-control changes;
- no executable-universe mutation;
- no scanner-result modification;
- no automatic state restoration;
- no mutation of account history or current positions;
- no fabricated blocker attribution.

## Validation Order After Railway Redeploy

1. `/paper/self-check`
2. `/paper/run-report-guard-status`
3. `/paper/state-provenance-status`
4. `/paper/missing-reason-trace-status`
5. `/paper/state-transaction-status`
6. `/paper/cycle-alignment-status`
7. `/paper/provider-health-status`
8. A single controlled `/paper/run` validation when no concurrent cycle is expected

Use `/paper/full-self-check` only for a failed routine check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Engineering Decision Log

### 2026-07-23 — Cycle alignment over cross-cycle comparison

Compare decision and blocker diagnostics only when they share the same cycle identifier because cross-cycle counts can differ legitimately.

### 2026-07-23 — Separate monotonic counters from contextual metrics

Monitor state revision, execution rows, wins, and losses as append-only; treat realized P&L, equity, and positions as contextual.

### 2026-07-24 — Trace missing blocker attribution without fabrication

Expose exact symbol/source evidence rather than synthesizing a reason.

### 2026-07-24 — Promote handoff to operating manual

Maintain dashboard, resume point, roadmap, sprint, ML roadmap, operations manual, decision log, and backlog.

### 2026-07-24 — Bound report-guard contention

Preserve serialized report substitution but reject concurrent run requests after a short bounded wait. This prevents sync-worker starvation while avoiding overlapping mutation of the global report-store function.

## Technical Debt and Enhancement Backlog

### Active / highest priority

- Validate bounded run-cycle guard v2 on Railway.
- Validate PR #6 diagnostics on Railway.
- Eliminate the final missing blocker-reason row through producer-contract repair.
- Collect multiple state-provenance observations and resolve any source divergence.
- Confirm decision/execution/outcome records meet ML-1 lineage requirements.

### Next

- Formalize the versioned ML training-table contract.
- Add dataset-readiness diagnostics for missing labels, duplicates, join failures, feature availability, and regime distribution.
- Define offline baseline models and evaluation metrics.
- Establish reproducible train/validation/test and walk-forward partitions.

### Future; explicit approval required

- Changes to scanner thresholds, entries, exits, risk, sizing, executable universe, or order behavior.
- ML influence over candidate ranking or confidence.
- Experimental capital allocation controlled by ML.
- Crypto-engine expansion or cross-asset portfolio optimization.
- Any live-trading authority.

## Files and Commits

- `run_report_guard.py`
  - bounded lock-wait recovery v2: `d1915e5a79282d0f6ccd541c6024421cf8ad86cd`
- `state_provenance_monitor.py`
  - v2 branch commit: `9ce6ddc4e03c38a7c9c4f5e103c2fbbad7f0892b`
- `missing_reason_trace_overlay.py`
  - initial trace overlay: `f42f4c985a7f1a7695c6cafdc46584ab379a63d8`
- `usercustomize.py`
  - missing-reason trace registration: `e0cbdd54775e2e6f17ced686b4e31e3f619d159f`
- PR #6
  - merged commit: `9998c597ef91b5d6edce47cdf481efcb6ac4cc90`

## Next Action

Validate the Railway redeploy beginning with `/paper/self-check`, then `/paper/run-report-guard-status`. Confirm the latest guard version and that manual cycle contention returns promptly rather than producing another Gunicorn worker timeout.
