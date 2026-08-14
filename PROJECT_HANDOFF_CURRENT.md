# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-14 after merged PR #56 and forensic PR #59–#63 review  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Canonical Railway paper service: `https://web-production-e1796.up.railway.app`

This file is the authoritative continuation point. Older handoffs are historical unless explicitly referenced here.

## Executive Status

Stable Core remains in repair/validation with Performance Lab shadow-only. Runtime is paper-only. Rules remain the sole execution authority. Live authority is disabled. ML/AI remains shadow-only. Do not change strategy, sizing, thresholds, risk limits, account state, live authority, or ML authority merely to resume trading.

## Canonical Accounting State

Current epoch: `stable-paper-v2-20260812-verified01`  
Prior epoch: `stable-paper-v1-20260810-clean01`  
Baseline: `verified_snapshot_with_open_position`  
Starting cash: approximately `$10,768.497731`  
Starting equity: approximately `$11,885.824057`  
Verified LRCX lot: `3.42486` long shares at approximately `$312.90`

The append-only canonical execution ledger remains authoritative for all new executions. Do not fabricate historical rows or revert to the old zero-position interpretation.

## Routine Validation

Routine audit:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

Full forensic audit:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Targeted source/exit guard status:

`https://web-production-e1796.up.railway.app/paper/exit-price-integrity-status`

Do not manually run `/paper/run` unless a future explicit validation plan requires it.

## PR #56 — Accepted Source-Level LRCX Containment — MERGED

PR #56, `Reject catastrophic terminal quotes before latest-price cache`, is merged into `main` at commit `03352a57d4a9ffde913ffd62f80f505a28e88793`.

Accepted behavior:

- preserves the existing entry-anchored paper exit quote-integrity guard as an independent second fail-closed layer;
- preserves normal 60-second valid-price caching;
- compares a fresh 1-day/5-minute terminal close with recent same-symbol prior closes;
- rejects catastrophic terminal prices at or below `0.40x` or at or above `2.50x` the recent median before cache/return;
- dynamically resolves the current `core.download_prices` owner on each uncached fetch so provider resilience ownership cannot be bypassed by startup order;
- changes no strategy, sizing, normal stops, risk thresholds, account state, live authority, or ML authority.

Both authoritative repository CI workflows passed on the corrected PR #56 head before merge.

Post-deploy `/paper/exit-price-integrity-status` confirmed version `paper-exit-price-integrity-2026-08-13-v2-source-plausibility`, `source_plausibility.installed: true`, and preserved the historical blocked LRCX attempt at `$18.401199340820312` versus verified entry `$312.90`. The existing exit guard must not be weakened or cleared.

## Current Runtime Blocker — Contaminated Intraday Peak Provenance

The source-level LRCX defect is contained, but the current risk halt remains because stored intraday peak provenance appears contaminated by a separate pre-fix UCTT bad quote.

Relevant current-epoch rows from the canonical audit:

- `entry` UCTT, **side `long`**, price `$93.22`;
- `partial_exit` UCTT, **side `long`**, price `$337.54`;
- final `exit` UCTT, **side `long`**, price `$94.025`.

The `$337.54` partial is approximately `3.62x` the entry and is implausible relative to the surrounding prices. Because it was a favorable spike on a **long** position, the adverse-only long exit guard does not establish the anomaly; the applicable provenance is the already-merged source-level terminal-price plausibility boundary, whose catastrophic high-side rule is symmetric at `>=2.50x`.

Current audit evidence previously showed current equity around `$13,321.43`, net daily loss `0.0%`, hard intraday threshold `2.5%`, and reported intraday drawdown around `11.73%`. Risk calibration trusts stored `risk_controls.day_peak_equity`, so a poisoned peak can keep the hard halt active even when current economics are not showing a daily loss.

**Do not clear the halt. Do not alter account state.**

## Forensic PR Review History

PR #58 was closed unmerged because it reused the suspect stored peak and modeled risk state incorrectly.

PR #59 was rejected because its threshold/metric handling was not decision-grade.

PR #60 was rejected because it still mishandled candidate-peak evidence and production semantics.

PR #61 was rejected because it did not reproduce the actual persisted partial-exit row shape.

PR #62 was rejected because it treated the partial row's ordinary execution `price` as though it were entry-price provenance, which caused the exact `$337.54` row to be skipped.

PR #63 was reviewed on 2026-08-14 and **closed unmerged**. It corrected the entry-price provenance issue but changed the actual production UCTT side from `long` to `short`. Its implementation then applied side-specific exit-integrity semantics, so it would not quarantine the real long `$93.22 -> $337.54` favorable spike. Both authoritative workflows on PR #63 were also `action_required`. A formal `REQUEST_CHANGES` review was submitted before closure.

No code from PR #58–#63 was merged into `main`.

## Active Replacement Work

A new repo-agent correction has been requested from current main. Required exact fixture and semantics:

1. entry UCTT `side=long`, `price=93.22`;
2. partial_exit UCTT `side=long`, `price=337.54`, with no `entry_price` on the partial row;
3. final exit UCTT `side=long`, `price=94.025`;
4. correlate the partial to the most recent prior same-symbol, same-side long entry;
5. quarantine **only** the `$337.54` partial because `337.54 / 93.22 >= 2.50` under the merged source-level terminal-price plausibility boundary;
6. do not pretend the position was short and do not use the adverse-only long exit guard to justify the favorable spike;
7. preserve source plausibility factors `0.40 / 2.50` and hard intraday threshold exactly `0.025`;
8. do not use stored `day_peak_equity` or `intraday_drawdown_pct` as candidate-peak support;
9. if independent peak evidence is absent, return `conclusion=insufficient_evidence` and `candidate_peak_equity=None`;
10. reporting-only and input-immutable; no runtime, persistence, risk, halt, account, ledger, live, or ML mutation.

Review the exact resulting PR diff and both authoritative workflows before advancement. Do not merge merely because tests are green if the production state shape or provenance is wrong.

## Risk Boundaries — Preserve

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`
- source terminal-price plausibility: `0.40x` minimum and `2.50x` maximum

No risk threshold is to be weakened to create trades or release the halt.

## Architecture Direction

Preferred direction remains clean side-by-side v2 core / explicit ownership: one persistent-state owner, one canonical ledger owner, one accounting owner, one cycle owner, one risk owner, one market-data owner, explicit paper/live separation, fail-closed safety, and ML shadow-only unless explicitly promoted.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated historical ledger rows.
- Rules remain sole execution authority.
- ML remains shadow-only for execution.
- No risk-threshold weakening merely to create trades.
- Do not alter account state to make an audit pass.
- Do not clear a genuine safety halt without diagnosing its cause.
- Preserve forensic evidence before deleting or migrating state.
- Prefer targeted correctness fixes over broad rewrites.
- Both authoritative GitHub CI workflows must pass before runtime changes are merged/deployed.

## Proactive Status / Next-Step Protocol

The user should not have to repeatedly ask `Done?` or `What next?`.

1. Continue routine investigation, fix, PR, CI, review, and handoff maintenance automatically within already-agreed scope.
2. When a task finishes, proactively report pass/fail and the immediate next action.
3. When work is still running, report what is in progress and what is being waited on.
4. If manual user action is unavoidable, provide exact numbered click-by-click instructions.
5. Do not ask the user to manually edit runtime code when a connector/agent path can do it.
6. Stop for new approval only for genuinely high-impact changes outside agreed scope, including live authority, ML execution authority, risk limits, strategy intent, or manual account-state alteration.

## Conversation Continuity Protocol

Warn before the active ChatGPT conversation becomes too long for safe continuation. Before recommending a new conversation:

1. update this handoff with all material branch/PR/commit/deployment status, blockers, latest validation evidence, safety boundaries, and exact next action;
2. then provide one exact copy/paste continuation command;
3. the user should never need to request this protocol again.

Continuation command:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Verify the current GitHub branch/PR/commit and latest canonical Railway daily audit before making changes. Continue from the exact next action documented in the handoff. Preserve all Stable Core safety, accounting, execution-authority, risk, paper-only, and ML-shadow boundaries. Do not restart completed historical investigations unless new evidence proves they are relevant. Continue routine in-scope fixes, PR review, CI validation, and handoff maintenance without waiting for repeated approvals. Proactively tell me when work completes, fails, is still in progress, or requires a manual step. If a manual step is unavoidable, give exact numbered instructions. Also follow the Conversation Continuity Protocol in PROJECT_HANDOFF_CURRENT.md.
```

## Exact Next Action

Wait for the new reporting-only forensic PR generated from the post-PR #63 correction request. Inspect the exact diff for the real **long-side** UCTT production rows and source-plausibility provenance, then inspect both authoritative CI workflows. Reject any patch that changes runtime behavior, state, guard thresholds, risk controls, live authority, ML authority, or that again alters the production trade shape. Only after a decision-grade read-only diagnostic is green should any separate persistent-state repair decision be considered.
