# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-14 after rejection of PR #67 and TEM duplicate-exit investigation retry  
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

The append-only canonical execution ledger remains authoritative. Do not fabricate, rewrite, or delete historical execution rows.

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

Post-deploy evidence confirmed the source guard is active. A later legitimate LRCX exit recorded near `$333.12`, while the historical blocked bad attempt remains approximately `$18.40` versus verified entry `$312.90`.

The existing source and exit quote-integrity guards must not be weakened or cleared.

## Historical Workflow Check

Repo-agent workflow `31737484525` completed successfully on 2026-08-13 from historical main commit `106a217ef60a6bc659ab2545ebf65e5cdc1e372e`. It is superseded by merged PR #56 and requires no further action.

## Current Highest-Priority Runtime Blocker — Duplicate TEM Full Exit

Fresh production audit generated `2026-08-14 11:31:52 CDT` exposed a new accounting-integrity defect in the active v2 epoch:

1. TEM `entry`, long `29.640567` @ `$54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`;
2. TEM full `exit`, long `29.640567` @ `$53.105`, execution `7b13d9194a23407f926667b2f48d4057`;
3. a second TEM full `exit`, long `29.640567` @ `$52.905`, execution `3530dbf965db4894ba93b7098cec3696`.

The second exit has no reconstructed position left to close. Audit result: `exit_exceeds_reconstructed_position`, `coverage_complete=false`, `economic_issue_count=1`, accounting integrity not reconciled, and journal recovery candidate not trusted. The current account has only QQQ open.

This is separate from the LRCX source fix and separate from the older UCTT contaminated-peak issue. Do not repair it by rewriting ledger history or account state. Required direction is a prospective, production-shaped duplicate-close/idempotency fix only after the actual canonical execution path is proven.

Issue #66 tracks this defect.

### PR #67 — Rejected and Closed Unmerged

PR #67 claimed a narrow TEM ownership fix but changed only `ml_recommendation_counterfactual_ledger.py`, a shadow/counterfactual labeling module, without proving it emitted the two canonical TEM executions. Exact diff was materially unsafe: 32 additions and 1,092 deletions, including removal of most of that module and unrelated global-name changes. Both authoritative workflows completed `action_required`.

A formal `REQUEST_CHANGES` review was submitted and PR #67 was closed unmerged. No code from PR #67 entered `main`.

A stricter repo-agent retry is running as workflow `31822658884` from main commit `163dfee70efadbc79b16c356b6ed456698695f86`. It must trace the actual functions that emitted the two canonical TEM exit execution IDs, prove the duplicate-dispatch/close-ownership mechanism, and only then propose the smallest prospective execution-boundary fix with an exact production-shaped regression. It must not touch ML shadow matching as a substitute for execution-path evidence.

## Remaining Separate Forensic Blocker — UCTT Contaminated Peak Provenance

Historical sequence:
1. UCTT `entry`, long, `$93.22`;
2. UCTT `partial_exit`, long, `$337.54`;
3. UCTT final `exit`, long, `$94.025`.

The `$337.54` partial is implausible and may have contaminated stored intraday peak state. Current policy remains conservative: do not use stored `risk_controls.day_peak_equity` or stored `intraday_drawdown_pct` as independent evidence for a corrected peak. If independent evidence is insufficient, report `insufficient_evidence` rather than alter state.

Do not clear the current halt or alter account state.

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
- No fabricated, deleted, or rewritten historical ledger rows.
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

Wait for repo-agent workflow `31822658884`. If it opens a PR, inspect the exact diff before considering advancement. Accept only a narrow prospective fix at the actual canonical paper execution/close boundary that prevents a second full close after the first has consumed the position, preserves all historical rows/state, includes the exact TEM production-shaped regression, and passes both authoritative workflows. Reject any ML-shadow-only explanation, broad rewrite, account-state repair, risk change, or quote-guard change. Do not merge automatically.