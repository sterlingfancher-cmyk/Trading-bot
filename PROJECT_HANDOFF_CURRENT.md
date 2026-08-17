# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-17 after evening runtime audit  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Canonical Railway paper service: `https://web-production-e1796.up.railway.app`

## Executive Status

Stable Core remains in repair/validation with Performance Lab shadow-only. Runtime remains paper-only. Rules remain the sole execution authority. Live authority is disabled. ML/AI remains shadow-only.

Morning audit generated `2026-08-17 11:22:11 CDT` showed runner pass, market-data pass, canonical execution ledger chain valid, risk controls pass with `halted=false`, and only the historical TEM duplicate-exit accounting defect remaining.

A later audit generated `2026-08-17 17:10:44 CDT` shows a new material risk-state event: account equity is approximately `$13,274.84` with QQQ/MCHP/AG open, realized today approximately `-$6.11`, unrealized approximately `+$11.18`, `net_daily_loss_pct=0.0`, but `intraday_drawdown_pct=21.259%` and the unchanged hard `2.5%` intraday drawdown halt is active. Runner and market-data status still pass, the canonical ledger chain remains valid, and no new accounting-error category appeared. This pattern strongly indicates a contaminated/transient intraday equity peak rather than a genuine 21.259% economic loss. Do not clear or weaken the halt until the peak source is identified.

Do not change strategy, sizing, thresholds, risk controls, account state, paper/live authority, or ML authority merely to make the audit pass.

## Canonical Accounting State

Current epoch: `stable-paper-v2-20260812-verified01`  
Baseline: `verified_snapshot_with_open_position`  
Starting cash: approximately `$10,768.497731`  
Starting equity: approximately `$11,885.824057`

Latest audit account snapshot (`2026-08-17 17:10:44 CDT`): cash approximately `$9,347.15`, equity approximately `$13,274.84`, open positions QQQ/MCHP/AG, realized today approximately `-$6.11`, unrealized approximately `+$11.18`.

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

Repo-agent workflow `31737484525` completed successfully on 2026-08-13 from historical main commit `106a217ef60a6bc659ab2545ebf65e5cdc1e372e`. GitHub reports no pull request attached to that workflow run. It is superseded by merged PR #56. No further action is required on that historical run.

## Current Highest-Priority Runtime Blocker — New Aug 17 Contaminated Intraday Peak / Risk Halt

The `2026-08-17 17:10:44 CDT` routine audit reports:
- equity approximately `$13,274.84`;
- realized today approximately `-$6.11`;
- unrealized approximately `+$11.18`;
- `net_daily_loss_pct=0.0`;
- `intraday_drawdown_pct=21.259%`;
- risk `halted=true` with unchanged reason `performance risk hard intraday drawdown halt (2.50%)`;
- runner pass and market-data pass;
- no new canonical accounting coverage issue beyond the historical TEM duplicate exit.

The morning audit from the same date had approximately `$13,298.86` equity and only `0.218%` intraday drawdown. The later 21.259% drawdown with essentially flat account economics implies the stored `day_peak_equity` was likely inflated by a transient valuation/quote event during the session. Candidate symbols active during the period include QQQ, MCHP, AG, plus entries/exits recorded for CLSK/BTDR as applicable in full history. Do not assume which symbol caused it until full runtime evidence identifies the offending quote/equity snapshot.

Required next evidence:
1. `/paper/exit-price-integrity-status` to confirm the merged source/exit guard remains installed and whether it recorded a block;
2. `/paper/daily-audit?full=1` to inspect position-level last prices, risk `day_peak_equity`, report/history evidence, and any source/plausibility diagnostics that can identify the transient peak;
3. do not clear the risk halt or rewrite peak/account state from inference alone.

A future fix, if needed, must address the actual source of peak contamination prospectively. Do not weaken the 2.5% risk threshold.

## Separate Historical Blocker — Duplicate TEM Full Exit

Production evidence in epoch `stable-paper-v2-20260812-verified01`:
1. TEM `entry`, long `29.640567` @ `$54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`, time `1786647398`;
2. TEM full `exit`, long `29.640567` @ `$53.105`, execution `7b13d9194a23407f926667b2f48d4057`, time `1786714863`;
3. second TEM full `exit`, long `29.640567` @ `$52.905`, execution `3530dbf965db4894ba93b7098cec3696`.

The second exit has no reconstructed position left to close. The 2026-08-17 evening audit still reports exactly this one historical issue: `exit_exceeds_reconstructed_position`, `coverage_complete=false`, `coverage_issue_count=1`, `economic_issue_count=1`. No additional unmatched exit/accounting issue appeared despite subsequent canonical activity. The journal recovery candidate remains untrusted because this historical defect is still present.

Static trace establishes:
- `app.exit_position()` mutates cash, removes the position, updates realized P/L and cooldown, then calls `record_trade("exit", ...)`;
- `canonical_execution_ledger.apply()` wraps `record_trade` and durably appends the canonical JSONL execution before the underlying state trade mirror;
- `run_cycle` persists `portfolio` later through `save_state(portfolio)`;
- persisted state and canonical execution durability are therefore not one atomic transaction.

Issue #66 tracks this defect.

### Rejected TEM PRs / Runs

- PR #67: ML-shadow matcher change, wrong execution boundary and broad deletion; closed unmerged.
- PR #68: unwired helper with non-production schema assumptions; closed unmerged.
- PR #69: evidence-only test with no production boundary fix; closed unmerged.
- Workflow `31838934941`: failed validation with `IndentationError`; no PR accepted.
- PR #70: broad persistence rewrite with wrong ledger/schema assumptions; closed unmerged.
- PR #71: guessed helper signatures and included the already-erroneous second exit in the causal fixture; closed unmerged.
- PR #72: did not force the real mounted-persistence branch and used non-production state shape; closed unmerged.
- PR #73: test-only restart/persistence evidence did not prove the causal second-exit path; both authoritative workflows were `action_required`; closed unmerged.
- PR #74 from workflow `31855867000`: rejected and closed unmerged. It replaced most of `canonical_execution_ledger.py`, changed the established `apply(core)` contract, changed the canonical ledger filename, and removed existing hash-chain/wrapper behavior. Both authoritative workflows were `action_required`.
- PR #75, `Add small duplicate-full-exit guard (canonical exit guard) with tests`: rejected and closed unmerged. It added an unwired helper rather than installing protection at the proven `app.exit_position()` runtime boundary and permitted exits when canonical ledger truth was unreadable/malformed. Both authoritative workflows completed `action_required`. No code from PR #75 entered `main`.
- Workflow `31878943252`: failed safely on 2026-08-15 with `RuntimeError: Agent proposed no files.` The constrained agent made no branch, PR, or runtime change rather than violating the required surgical/fail-closed scope.

## Current TEM Repair Direction

Do not replace or redesign `canonical_execution_ledger.py`. Its existing API, append-only JSONL filename, hash-chain verification, `record_trade` wrapping, status route behavior, and startup composition must remain intact.

A permissible prospective TEM fix, only if supported by code evidence, is a tiny fail-closed guard before full-exit mutation: for a candidate full exit, inspect authoritative current-epoch canonical rows for the same symbol/side. If at least one canonical entry exists and canonical net open quantity is already `<= epsilon`, block the second exit before cash/P&L/position/ledger mutation and emit a diagnostic/halt marker. This must not infer closure for verified-snapshot baseline positions that have no canonical entry.

Any such guard must use the existing canonical ledger's own parsing/hash-chain semantics. Missing, unreadable, malformed, or hash-invalid canonical evidence must not silently become permission for a full exit under a duplicate-exit guard. Do not add an unwired helper and call it complete.

Prefer a surgical integration immediately at the proven `app.exit_position()` pre-mutation boundary while preserving all existing canonical-ledger behavior. Do not change the existing `apply(core)` signature. Do not change `LEDGER_FILE = .../canonical_execution_ledger.jsonl`. Do not weaken chain verification or canonical append ordering.

Regression must use the literal TEM sequence: entry `d647...` 29.640567 @ 54.885, first exit `7b13...` 29.640567 @ 53.105, then a stale/resurrected second exit attempt @ 52.905 which must create no cash/P&L/canonical mutation.

Do not launch another speculative repo-agent retry merely because the audit still carries the historical TEM row. A future runtime code change still requires a concretely reviewable surgical implementation at the proven boundary.

## Remaining Separate Forensic History — UCTT Contaminated Peak Provenance

Historical sequence: UCTT entry long `$93.22`, partial exit `$337.54`, final exit `$94.025`.

The `$337.54` partial is implausible and likely contaminated historical intraday peak state. The morning 2026-08-17 daily risk state had reset cleanly, but the evening session developed a new independent contaminated-peak pattern. Do not assume the evening event is the same UCTT history; UCTT is no longer open and the new event must be traced from current-session evidence.

## Risk Boundaries — Preserve

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`
- source terminal-price plausibility: `0.40x` minimum / `2.50x` maximum

No risk threshold is to be weakened to create trades or make an audit pass.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- No fabricated, deleted, rewritten, or manually edited historical ledger rows.
- Rules remain sole execution authority.
- ML remains shadow-only for execution.
- Do not alter account state to make an audit pass.
- Do not manually clear the current Aug 17 risk halt before identifying its contaminated-peak source.
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

First priority is the new Aug 17 evening contaminated-peak/risk-halt event. Obtain `/paper/exit-price-integrity-status` and `/paper/daily-audit?full=1`. Identify the actual source of the transient peak before any code or state change. Do not clear the halt manually and do not weaken the 2.5% threshold. If the source guard reports a new block or the full audit isolates a current symbol/price anomaly, trace that exact source path and only then consider a narrow prospective fix.

For TEM, the evening runtime audit still shows the same single historical duplicate-exit accounting defect and no new accounting error category across later canonical activity. No new TEM PR currently qualifies for advancement. Do not create another broad canonical-ledger rewrite, unwired helper, or speculative agent retry.

For LRCX, do not modify merged PR #56 unless new deployed evidence proves a new source-level quote plausibility defect. Historical repo-agent workflow `31737484525` is complete, has no attached PR, and is superseded by PR #56. Do not merge automatically.