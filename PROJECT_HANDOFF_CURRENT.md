# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-14 after merged PR #56 and post-deploy quote/risk forensics  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Canonical Railway paper service: `https://web-production-e1796.up.railway.app`

This file is the authoritative continuation point. Older `PROJECT_HANDOFF_*` files are historical context only unless this file explicitly references them.

## Executive Status

The project remains in **Stable Core repair/validation + Performance Lab shadow** mode.

Runtime remains **paper-only**. Rules remain the sole execution authority. Live authority is disabled. ML/AI, MAE/MFE optimization, crypto/multi-asset ranking, LONA, adaptive policies, and other research systems remain shadow/research-only unless an explicit later promotion decision is made.

The correct architectural direction remains: preserve the performance engine, simplify ownership/runtime plumbing, and avoid broad wrapper-style repairs when a narrow correctness fix is available.

## Canonical Service / State

Use only this Railway service for Stable Paper validation:

`https://web-production-e1796.up.railway.app`

Do **not** use `trading-bot-clean.up.railway.app`; it is attached to a stale/legacy persistent-state lineage.

Canonical persistent state remains `/app/data/state.json`.

## Current Accounting Epoch — Authoritative

Current epoch: `stable-paper-v2-20260812-verified01`  
Prior epoch: `stable-paper-v1-20260810-clean01`  
Baseline type: `verified_snapshot_with_open_position`  
Historical recovery decision: `verified_snapshot_rollforward`

Verified v2 starting state remains:

- starting cash: approximately `$10,768.497731`
- starting equity: approximately `$11,885.824057`
- verified open LRCX lot: `3.42486` long shares at approximately `$312.90`
- historical evidence archived
- forward validation required

Do not revert to the old v1 zero-position interpretation and do not fabricate historical executions.

## Canonical Execution Ledger

The append-only canonical execution ledger remains authoritative for new executions.

Required invariants:

- `chain_valid: true`
- `authoritative_for_new_executions: true`
- ledger epoch equals `stable-paper-v2-20260812-verified01`
- every new state execution maps to a canonical `execution_id`
- no fabricated rows

## Routine Operator Test

Routine:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

Full forensic detail only when needed:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Targeted diagnostics:

- `/paper/runtime-errors`
- `/paper/exit-price-integrity-status`
- `/paper/state-persistence-contract-status`
- `/bootstrap-status`

Do not manually run `/paper/run` unless a future explicit validation plan requires it.

## PR #56 — Source-Level LRCX Quote Plausibility Fix — MERGED

PR #56, `Reject catastrophic terminal quotes before latest-price cache`, is merged into `main` at merge commit:

`03352a57d4a9ffde913ffd62f80f505a28e88793`

Accepted head before merge:

`51007a9e1b9951e70570be40b2a1860af87e4625`

The merged change is the accepted narrow source-level containment for the proven LRCX bad quote path:

- preserves the existing paper exit-integrity guard as an independent second fail-closed layer;
- preserves the normal 60-second valid-price cache behavior;
- compares a fresh 1-day/5-minute terminal close with recent same-symbol prior closes;
- rejects catastrophic terminal outliers before cache/return;
- dynamically resolves the current `core.download_prices` owner at each fresh fetch so later market-data resilience wrapping cannot be bypassed by startup order;
- does not alter strategy, sizing, thresholds, normal stops, account state, order authority, live authority, or ML authority.

Both authoritative repository CI workflows passed on the corrected PR head before merge.

## Post-Deploy Source-Guard Evidence

Canonical `/paper/exit-price-integrity-status` after deployment reported:

- `status: ok`
- `overall: pass`
- version `paper-exit-price-integrity-2026-08-13-v2-source-plausibility`
- `source_plausibility.installed: true`
- recent-prior-bars: `24`
- minimum-prior-bars: `6`
- minimum price ratio: `0.4`
- maximum price ratio: `2.5`

The endpoint still preserves the historical active LRCX block evidence:

- boundary: `exit_position`
- symbol: `LRCX`
- verified entry: `$312.90`
- attempted exit: `$18.401199340820312`
- price/entry ratio: approximately `0.05881`
- reason: `catastrophic_long_exit_price_outlier`

This confirms the source-level protection is installed without weakening the existing fail-closed exit guard.

## Current Runtime Blocker — Contaminated Intraday Peak Provenance

The source-level LRCX defect is contained, but the canonical full daily audit still reports a risk halt:

- current equity: approximately `$13,321.43`
- net daily loss: `0.0%`
- hard intraday drawdown threshold: `2.5%`
- reported intraday drawdown: approximately `11.73%`
- halt reason: `performance risk hard intraday drawdown halt (2.50%)`
- self-defense active: `true`

Current-epoch execution evidence includes:

- UCTT entry at `$93.22`
- UCTT partial exit at `$337.54`
- UCTT final exit at `$94.025`

The `$337.54` partial exit is economically implausible relative to the surrounding UCTT prices and occurred before PR #56 was deployed. Current evidence therefore points to contaminated `day_peak_equity` provenance from the earlier bad quote rather than a current economic loss.

The risk calibration currently computes intraday drawdown from the stored `risk_controls.day_peak_equity`, so an inflated persisted peak can legitimately keep the 2.5% hard halt active until provenance is proven and any repair is separately authorized.

**Do not clear or weaken the halt. Do not alter account state.**

## Rejected Forensic Attempt — PR #58

PR #58, `Fix forensic_intraday_peak_diagnostic indentation and add focused reporting + tests`, was reviewed and **closed unmerged**.

Reasons it was not safe to advance:

- candidate corrected peak reused the suspect stored peak, so contaminated evidence could not be excluded;
- the diagnostic modeled risk fields at the wrong state level instead of canonical `portfolio["risk_controls"]` structure;
- both authoritative workflows were `action_required`;
- it was therefore not decision-grade evidence for a state-repair decision.

No runtime or account-state change from PR #58 was accepted.

## Follow-Up Repo-Agent Outcomes

Follow-up repo-agent workflow `31766243285` failed before producing an acceptable replacement PR. Its proposal was invalid JSON and attempted to broaden into `performance_risk_calibration.py`, outside the permitted reporting-only forensic scope. No code from that run was accepted.

A later documentation-only repo-agent run `31769443049` also failed safely because `scripts/repo_agent.py` intentionally protects `PROJECT_HANDOFF_CURRENT.md` from agent modification. The failure was:

`RuntimeError: Agent attempted to modify protected path: PROJECT_HANDOFF_CURRENT.md`

That is a guardrail behavior, not a runtime-bot failure. This handoff is therefore being maintained through the connected GitHub workflow instead of bypassing the repo-agent path restriction.

## Risk Boundaries — Preserve

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`

Do not weaken risk controls to create trades or accelerate validation.

The paper exit quote-integrity guard blocks long exit prices at or below 40% of entry and short exit prices at or above 2.5x entry. Preserve it unless later evidence proves the guard itself is incorrect.

## Architecture Direction

Preferred direction remains **clean side-by-side v2 core / explicit ownership**, rather than indefinitely extending the legacy wrapper graph.

Target ownership model:

- one authoritative persistent state owner
- one canonical execution ledger owner
- one accounting owner
- one orchestration/cycle owner
- one risk owner
- one market-data owner
- explicit paper/live separation
- no migration logic in normal steady-state startup
- no duplicate state owners
- fail-closed risk behavior
- ML shadow-only unless explicitly promoted
- reproducible CI and post-deploy validation

Do not destabilize the current Stable Paper runtime while building/refactoring toward that model.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated historical ledger rows.
- Rules remain sole execution authority.
- ML remains shadow-only for execution.
- Crypto/multi-asset execution remains disabled.
- No risk-threshold weakening merely to create trades.
- Do not alter account state to make an audit pass.
- Do not clear a genuine safety halt without diagnosing its cause.
- Preserve forensic evidence before deleting or migrating state.
- Prefer targeted correctness fixes over broad rewrites.
- Both authoritative GitHub CI workflows must pass before runtime changes are merged/deployed.

## User Operating Preferences — Permanent Project Protocol

### Proactive Status / Next-Step Protocol

The user should **not** have to repeatedly ask `Done?` or `What next?`.

During active project work:

1. Continue routine investigation/fix/PR/CI/review work automatically when it is within the already-agreed scope.
2. When a task finishes, proactively report whether it passed or failed and immediately state the next action.
3. When a task is still running, proactively state what is still in progress and what is being waited on.
4. If a manual user action becomes unavoidable, provide exact numbered step-by-step instructions automatically, including exactly what to click/open and what result to send back.
5. Do not ask the user to manually edit Python/runtime code when a GitHub/agent/connector path can perform the change.
6. Stop for new approval only for genuinely high-impact actions outside the agreed scope, such as changing live authority, ML execution authority, risk limits, strategy intent, or manually altering account state.

### Conversation Continuity Protocol

Proactively warn the user **before** the current ChatGPT conversation becomes too long for safe continuity.

Before recommending a new conversation:

1. Update this `PROJECT_HANDOFF_CURRENT.md` with all material current state.
2. Record current branch/PR/commit/deployment status, unresolved blocker(s), latest validation evidence, safety boundaries, and exact next action.
3. Then provide one exact copy/paste continuation command for the new conversation.
4. The user should never need to request this protocol again.

Default continuation command template:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Verify the current GitHub branch/PR/commit and latest canonical Railway daily audit before making changes. Continue from the exact next action documented in the handoff. Preserve all Stable Core safety, accounting, execution-authority, risk, paper-only, and ML-shadow boundaries. Do not restart completed historical investigations unless new evidence proves they are relevant. Continue routine in-scope fixes, PR review, CI validation, and handoff maintenance without waiting for repeated approvals. Proactively tell me when work completes, fails, is still in progress, or requires a manual step. If a manual step is unavoidable, give exact numbered instructions. Also follow the Conversation Continuity Protocol in PROJECT_HANDOFF_CURRENT.md: warn me before this conversation becomes too long, update the handoff completely, and give me the exact continuation command for the next chat.
```

## Exact Next Action

Do **not** mutate persistent state or clear the active halt.

Obtain a narrow, paper-only, **read-only forensic diagnostic** that uses the canonical nested `portfolio["risk_controls"]` state and actual current-epoch execution rows. It must:

1. report stored day-start equity, stored day-peak equity, current equity, and the resulting current intraday drawdown;
2. identify and quarantine the UCTT `$337.54` partial exit as unsupported peak evidence rather than reusing the suspect stored peak;
3. reconstruct a candidate supportable intraday peak only from verified current-epoch equity/execution evidence that is independent of the contaminated quote;
4. report whether the existing 2.5% hard intraday-drawdown halt would still be warranted under that candidate;
5. remain reporting-only: no cash, position, trade, ledger, P&L, risk-control, threshold, halt, live-authority, or ML-authority mutation;
6. add focused tests reproducing the production nested state shape and proving no mutation;
7. run both authoritative repository CI workflows;
8. review the exact diff before any merge.

Only after that evidence is green and decision-grade should a separate explicit state-repair decision be considered.
