# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-14 after PR #65 rejection  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Canonical Railway paper service: `https://web-production-e1796.up.railway.app`

## Executive Status

Stable Core remains in repair/validation with Performance Lab shadow-only. Runtime remains paper-only. Rules remain the sole execution authority. Live authority is disabled. ML/AI remains shadow-only.

Do not change strategy, sizing, thresholds, risk controls, account state, halt state, paper/live authority, or ML authority merely to resume trading.

## Canonical Accounting State

Current epoch: `stable-paper-v2-20260812-verified01`  
Prior epoch: `stable-paper-v1-20260810-clean01`  
Baseline: `verified_snapshot_with_open_position`  
Starting cash: approximately `$10,768.497731`  
Starting equity: approximately `$11,885.824057`  
Verified LRCX lot: `3.42486` long shares at approximately `$312.90`

The append-only canonical execution ledger remains authoritative. Do not fabricate historical rows or revert to the old zero-position interpretation.

## Routine Validation

Routine audit: `https://web-production-e1796.up.railway.app/paper/daily-audit`  
Full forensic audit: `https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`  
Source/exit guard status: `https://web-production-e1796.up.railway.app/paper/exit-price-integrity-status`

Do not manually run `/paper/run` unless an explicit future validation plan requires it.

## LRCX Bad-Quote Source Fix — Accepted and Merged

PR #56, `Reject catastrophic terminal quotes before latest-price cache`, is merged into `main` at commit `03352a57d4a9ffde913ffd62f80f505a28e88793`.

Accepted behavior:

- preserves the existing entry-anchored paper exit quote-integrity guard as an independent fail-closed layer;
- preserves normal 60-second valid-price caching;
- validates a fresh terminal close against recent same-symbol prior closes;
- rejects catastrophic source prices at or below `0.40x` or at or above `2.50x` the recent median before cache/return;
- dynamically resolves the current `core.download_prices` owner so startup order cannot bypass provider resilience;
- changes no strategy, sizing, normal stops, risk thresholds, account state, live authority, or ML authority.

Both authoritative repository workflows passed before PR #56 was merged. Post-deploy source status confirmed source plausibility installed and preserved the historical LRCX blocked attempt at approximately `$18.40` versus verified entry `$312.90`.

The existing exit quote-integrity guard must not be weakened or cleared.

## Historical Workflow Check

Repo-agent workflow `31737484525` completed successfully on 2026-08-13 from historical main commit `106a217ef60a6bc659ab2545ebf65e5cdc1e372e`. It is superseded by the later merged PR #56 state and requires no further action.

## Remaining Blocker — UCTT Contaminated Peak Provenance

The LRCX source defect is contained. A separate pre-fix UCTT quote anomaly remains relevant to the persisted intraday-peak risk halt:

1. `entry` UCTT, `side=long`, `price=93.22`;
2. `partial_exit` UCTT, `side=long`, `price=337.54`, with no `entry_price` on that row;
3. final `exit` UCTT, `side=long`, `price=94.025`.

The `$337.54` partial is approximately `3.62x` the entry and is implausible relative to surrounding execution prices. Current forensic policy is conservative: do not use stored `risk_controls.day_peak_equity` or stored `intraday_drawdown_pct` as independent support for any candidate corrected peak. If independent evidence is insufficient, report `insufficient_evidence` rather than alter state.

**Do not clear the halt. Do not alter account state.**

## Forensic PR Review History

PR #58 through PR #65 were all rejected/closed unmerged. No code from these forensic attempts entered `main`.

PR #65 was produced by repo-agent workflow `31795511783` from unchanged main commit `03352a57d4a9ffde913ffd62f80f505a28e88793`. Its scope was reporting-only, but the exact diff contained a fatal correctness defect: inside the trade scan it evaluated `any(token in ... for k in (...))` even though `token` was undefined. An ordinary `entry` row would therefore execute that branch and raise `NameError` before the production-shaped sequence could be analyzed. Both authoritative workflows on PR #65 completed `action_required`. A formal `REQUEST_CHANGES` review was submitted and PR #65 was closed unmerged.

Do not continue generating forensic PRs merely to satisfy synthetic tests. Any future forensic helper must first be justified as necessary for the source-level repair workflow and must pass exact diff review plus both authoritative workflows.

## Risk Boundaries — Preserve

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`
- source terminal-price plausibility: `0.40x` minimum and `2.50x` maximum

No risk threshold is to be weakened to create trades or release the halt.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated historical ledger rows.
- Rules remain sole execution authority.
- ML remains shadow-only for execution.
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

Treat PR #56 as the accepted source-level containment and do not modify it unless new deployed evidence proves a source-level defect remains. Do not spawn another forensic helper PR automatically. On the next meaningful runtime validation, inspect the canonical `/paper/daily-audit` and `/paper/exit-price-integrity-status`. Only if those show a new source-level quote-plausibility failure should a narrow source fix be considered. The persisted UCTT/risk-halt provenance remains a separate forensic/account-state decision and must not be resolved by changing state or weakening guards without independent evidence and explicit review.
