# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-14 after rejection of PR #70  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Canonical Railway paper service: `https://web-production-e1796.up.railway.app`

## Executive Status

Stable Core remains in repair/validation with Performance Lab shadow-only. Runtime remains paper-only. Rules remain the sole execution authority. Live authority is disabled. ML/AI remains shadow-only.

Do not change strategy, sizing, thresholds, risk controls, account state, halt state, paper/live authority, or ML authority merely to resume trading.

## Canonical Accounting State

Current epoch: `stable-paper-v2-20260812-verified01`  
Baseline: `verified_snapshot_with_open_position`  
Starting cash: approximately `$10,768.497731`  
Starting equity: approximately `$11,885.824057`

The append-only canonical execution ledger remains authoritative. Do not fabricate, rewrite, delete, or manually repair historical execution rows.

## Routine Validation

Routine audit: `https://web-production-e1796.up.railway.app/paper/daily-audit`  
Full forensic audit: `https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`  
Source/exit guard status: `https://web-production-e1796.up.railway.app/paper/exit-price-integrity-status`

Do not manually run `/paper/run` unless an explicit future validation plan requires it.

## LRCX Bad-Quote Source Fix — Accepted and Merged

PR #56, `Reject catastrophic terminal quotes before latest-price cache`, is merged into `main` at commit `03352a57d4a9ffde913ffd62f80f505a28e88793`.

Accepted behavior:
- preserves the existing entry-anchored paper exit quote-integrity guard as an independent fail-closed layer;
- preserves normal valid-price caching;
- validates fresh terminal prices against recent same-symbol prior closes;
- rejects catastrophic source prices at or below `0.40x` or at or above `2.50x` the recent median before cache/return;
- dynamically resolves the current `core.download_prices` owner;
- changes no strategy, sizing, normal stops, risk thresholds, account state, live authority, or ML authority.

Post-deploy evidence confirmed the source guard is active. A later legitimate LRCX exit recorded near `$333.12`, while the historical bad attempt was approximately `$18.40` versus verified entry approximately `$312.90`.

The existing source and exit quote-integrity guards must not be weakened or cleared.

## Historical Workflow Check

Repo-agent workflow `31737484525` completed successfully on 2026-08-13 from historical main commit `106a217ef60a6bc659ab2545ebf65e5cdc1e372e`. It produced no directly actionable PR and is superseded by merged PR #56. No further action is required on that historical run.

## Current Highest-Priority Runtime Blocker — Duplicate TEM Full Exit

Production evidence in epoch `stable-paper-v2-20260812-verified01`:
1. TEM `entry`, long `29.640567` @ `$54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`;
2. TEM full `exit`, long `29.640567` @ `$53.105`, execution `7b13d9194a23407f926667b2f48d4057`;
3. second TEM full `exit`, long `29.640567` @ `$52.905`, execution `3530dbf965db4894ba93b7098cec3696`.

The second exit has no reconstructed position left to close. Audit reports `exit_exceeds_reconstructed_position`, accounting coverage incomplete, economic issue count 1, and journal recovery not trusted.

Static trace now establishes the relevant boundaries:
- `app.exit_position()` mutates cash, deletes the position, updates realized P/L and cooldown, then calls `record_trade("exit", ...)`;
- `canonical_execution_ledger.apply()` wraps `record_trade` and durably appends the canonical JSONL execution before the underlying state trade mirror;
- `run_cycle` persists `portfolio` later through `save_state(portfolio)`;
- `state_persistence_contract.apply()` may replace live in-memory portfolio state with a materially richer persisted snapshot on startup.

Therefore stale persisted-state resurrection after a durable canonical close remains a credible mechanism, but no runtime repair is accepted until the implementation matches the literal canonical JSONL schema and preserves the existing persistence contract.

Issue #66 tracks this defect.

### Rejected TEM PRs

- PR #67: ML-shadow matcher change, broad deletion, wrong execution boundary; closed unmerged.
- PR #68: unwired helper with non-production `entry_execution_id` and `size/qty` assumptions; closed unmerged.
- PR #69: evidence-only test, no production fix; closed unmerged.
- Workflow `31838934941`: failed validation with `IndentationError`; no PR accepted.
- PR #70 from workflow `31841199828`: **rejected and closed unmerged**. It replaced most of `state_persistence_contract.py` despite the surgical-patch requirement (`315` additions / `271` deletions), removed existing persistence behavior, looked for `canonical_execution_ledger.json` instead of the actual `canonical_execution_ledger.jsonl`, and depended on entry-ID links that the real TEM exit rows do not contain. Both authoritative workflows on head `a353d346e7c3116cce59097bb8daed355f5430b5` completed `action_required`.

No code from PR #70 entered `main`.

## Remaining Separate Forensic Blocker — UCTT Contaminated Peak Provenance

Historical sequence:
1. UCTT entry long `$93.22`;
2. UCTT partial exit `$337.54`;
3. UCTT final exit `$94.025`.

The `$337.54` partial is implausible and may have contaminated stored intraday peak state. Do not use stored `risk_controls.day_peak_equity` or stored `intraday_drawdown_pct` as independent evidence for a corrected peak. If independent evidence is insufficient, report `insufficient_evidence` rather than alter state.

Do not clear the current halt or alter account state.

## Risk Boundaries — Preserve

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`
- source terminal-price plausibility: `0.40x` minimum / `2.50x` maximum

No risk threshold is to be weakened to create trades or release the halt.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated, deleted, rewritten, or manually edited historical ledger rows.
- Rules remain sole execution authority.
- ML remains shadow-only for execution.
- Do not alter account state to make an audit pass.
- Do not clear a genuine safety halt without diagnosing its cause.
- Preserve forensic evidence before deleting or migrating state.
- Prefer targeted correctness fixes over broad rewrites.
- Both authoritative GitHub CI workflows must pass before runtime changes are merged/deployed.

## Proactive Status / Next-Step Protocol

1. Continue routine investigation, fix, PR, CI, review, and handoff maintenance automatically within already-agreed scope.
2. Proactively report pass/fail and the immediate next action when material work completes.
3. If work is still running, report what is in progress only when meaningful.
4. If manual user action is unavoidable, provide exact numbered click-by-click instructions.
5. Do not ask the user to manually edit runtime code when a connector/agent path can do it.
6. Stop for new approval only for genuinely high-impact changes outside agreed scope, including live authority, ML execution authority, risk limits, strategy intent, or manual account-state alteration.

## Conversation Continuity Protocol

Warn before the active ChatGPT conversation becomes too long for safe continuation. Before recommending a new conversation:
1. update this handoff with all material branch/PR/commit/deployment status, blockers, latest validation evidence, safety boundaries, and exact next action;
2. provide one exact copy/paste continuation command;
3. the user should never need to request this protocol again.

Continuation command:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Verify the current GitHub branch/PR/commit and latest canonical Railway daily audit before making changes. Continue from the exact next action documented in the handoff. Preserve all Stable Core safety, accounting, execution-authority, risk, paper-only, and ML-shadow boundaries. Do not restart completed historical investigations unless new evidence proves they are relevant. Continue routine in-scope fixes, PR review, CI validation, and handoff maintenance without waiting for repeated approvals. Proactively tell me when work completes, fails, is still in progress, or requires a manual step. If a manual step is unavoidable, give exact numbered instructions. Also follow the Conversation Continuity Protocol in PROJECT_HANDOFF_CURRENT.md.
```

## Exact Next Action

Do not modify merged PR #56 unless new deployed evidence proves a new source-level quote plausibility defect.

For TEM, do **not** generate another broad persistence rewrite or generic provenance helper. The next candidate must preserve the existing `state_persistence_contract.py` behavior and use the actual `canonical_execution_ledger.jsonl` schema. Before any reload that would reintroduce an open position, correlate the persisted position lifecycle using literal production trade/ledger fields (`accounting_epoch_id`, `action`, `execution_id`, `price`, `shares`, `side`, `symbol`, timestamps and canonical metadata) rather than invented `entry_execution_id` links. Only if that exact lifecycle proves the position was already fully closed may a narrow fail-closed reload guard be proposed. It must prevent the stale reload before any later second close can mutate cash/P&L or append another canonical execution. Any PR must preserve historical rows/state, existing persistence/status behavior, all risk and authority boundaries, and pass both authoritative workflows. Do not merge automatically.