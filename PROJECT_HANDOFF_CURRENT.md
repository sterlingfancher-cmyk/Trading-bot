# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-21 10:15 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Current `main` before this handoff-only PR: `0874368ad5bf303337b8c94ed1c9ae967c2231b5` (`Update authoritative handoff through Aug 21 (#99)`)  
Canonical Railway paper service: `https://trading-bot-clean.up.railway.app`

## Communication / Continuity Rule

Keep Trading-bot progress communication in the **currently active ChatGPT project conversation**. This is not permanently tied to one specific thread. When the project intentionally moves to a new ChatGPT conversation, update this handoff first, use the continuation command at the bottom, and treat the new conversation as the active project chat.

Do not let project-specific monitoring tasks continue posting into an old/stale project conversation. On 2026-08-21 the `Trading System Completion` and `QQQ Repair Watch` monitoring tasks were disabled; `Trading Architecture Builder` was already disabled. They should remain disabled unless a future current project chat intentionally re-establishes monitoring in that active conversation.

Repository handoff maintenance remains mandatory so a new conversation can recover exact state without relying on prior-chat memory.

## Executive Status

Operational stabilization is still blocked by GitHub Issue #82. Runtime remains paper-only. Rules remain the sole execution authority. Live authority is disabled. ML/AI remains shadow-only for execution.

The fresh-day protection is now behaving fail-closed, but the authoritative paper account snapshot is corrupted and cannot seed a new risk day. Current live/on-disk state is approximately:
- `cash=-26064.308325`
- `equity=-26064.31`
- no open positions
- `realized_total=-94929.16`

The risk state remains stale from 2026-08-20 with:
- `day_start_equity=-26064.31`
- `day_peak_equity=0.01`
- `halted=true`
- `halt_reason='daily loss limit hit (3.0%)'`
- `fresh_day_reset_pending=true`

Do not clear the halt, rewrite the risk peak, force a fresh-day baseline, rewrite canonical ledger rows, or overwrite the account from an incomplete reconstruction merely to make an audit pass.

## 2026-08-21 Settled Runtime Evidence After PR #98

### Fresh-day guard

`/paper/fresh-day-check`:
- `baseline_status=pending`
- risk date remains `2026-08-20`
- `day_start_equity=-26064.31`
- `day_peak_equity=0.01`
- `fresh_day_reset_pending=true`
- `halted=true`
- `intraday_drawdown_pct=0.0`

`/paper/fresh-risk-day-baseline-guard-status`:
- guard installed / overall pass
- `current_equity_sane=false`
- `day_start_equity_sane=false`
- `day_peak_equity_sane=false`
- `fresh_day_reset_pending=true`
- prospective only; no current-day rewrite, halt clear, peak rewrite, historical-accounting edit, order placement, strategy/sizing/threshold/live/ML authority change

Interpretation: the guard is functioning correctly and refusing to manufacture a 2026-08-21 risk baseline from invalid active equity.

### Compact self-check

`/paper/self-check` at `2026-08-21 09:51:12 CDT`:
- overall `warn`, response/status `ok`
- account: cash `-26064.308324919723`, equity `-26064.31`, positions `[]`, realized today `0.0`, realized total `-94929.16`, unrealized `0.0`
- auto runner enabled and observed active; no current runner error
- all 9 bounded runtime component checks pass
- scanner/entry composition ownership checks pass
- runtime shadow capture parity passes
- risk remains halted/self-defense-active because of the stale daily-loss halt state

### Full daily audit

`/paper/daily-audit?full=1` at `2026-08-21 09:52:32 CDT`:
- overall `fail` because risk remains halted and accounting integrity is not reconciled
- runner liveness passes; no active recursion/runtime error
- market-data/provider accounting is complete and clean at snapshot
- persistent volume is healthy; `/data/state.json` exists; in-memory/on-disk richness match; no detected JSON corruption
- PR #98 therefore appears to have stopped the diagnostic X-Ray overwrite path, but the state now being faithfully persisted is already contaminated
- accounting reconstruction reports approximately `cash/equity=10724.779592`, `realized_total=724.779592`, zero positions
- reconstruction coverage is incomplete with 193 ignored/unmatched exit rows, mostly legacy rows beginning 2026-08-07
- separate ledger-economic integrity also fails
- therefore `$10,724.779592` is evidence only and **must not be promoted automatically into authoritative state**

### Canonical execution ledger

`/paper/canonical-execution-ledger-status`:
- `status=ok`, `overall=pass`
- `append_only=true`
- `hook_applied=true`
- `authoritative_for_new_executions=true`
- `chain_valid=true`
- `parse_error_count=0`, `chain_error_count=0`, `errors=[]`
- `row_count=55`
- `current_epoch_id=legacy-pre-stable-core`
- `current_epoch_rows=55`
- last execution id `e746b3e674654f9199402c8904df1f43`

The hash chain is healthy and must remain untouched. The active portfolio no longer exposes `stable-paper-v2-20260812-verified01`; all 55 surviving canonical rows are currently classified by the runtime under `legacy-pre-stable-core`. Do not relabel or rewrite them.

### Clean accounting epoch status — latest provenance evidence

`/paper/clean-accounting-epoch-status` at approximately 10:15 CDT returned:
- `status=blocked`, `overall=warn`
- `marker_status=null`
- `forensic_archive_dir=null`
- `historical_recovery_decision=null`
- `historical_evidence_archived=false`
- `clean_start=false`
- `zero_trade_baseline=false`
- `validation_hold=false`

Important interpretation: the returned `epoch_id=stable-paper-v1-20260810-clean01` is **not proof that the clean epoch is active**. In `clean_accounting_epoch.status_payload()`, when the target epoch is not active, the endpoint reports the target constant as `epoch_id` while `clean_start`, `zero_trade_baseline`, recovery decision, archive flag, and marker reveal the real inactive state. The null marker/archive plus false clean/zero-trade flags mean the current active state does not contain a valid active clean-epoch record and the expected clean-epoch completion marker is not present at the configured marker path.

Combined with the canonical ledger reporting `legacy-pre-stable-core`, this strengthens the hypothesis that an older pre-stable-core snapshot was resurrected before PR #98 stopped X-Ray from replacing live state. It does **not** yet prove which backup/file did it.

## Issue #82 — Stabilization Exit Gate

Issue #82 remains open and authoritative.

Already protected prospectively:
- PR #56 source terminal-price plausibility guard
- PR #79 fresh cached-price provenance/plausibility validation
- PR #80 catastrophic persisted `last_price` valuation fallback guard
- PR #81 canonical pre-mutation duplicate-full-exit guard
- PR #83 fresh-day baseline sanity guard
- PR #87 pre-WSGI fresh-day guard installation order
- PR #98 removal of diagnostic X-Ray independent authoritative state I/O

Remaining acceptance:
1. sane fresh-day risk initialization from a protected authoritative valuation;
2. one normal forward paper market session after that clean reset;
3. evidence-based historical-accounting disposition without rewriting immutable execution history;
4. clean active audit with sane valuation, healthy runner/market data, valid canonical chain, no new active coverage/economic issue, and risk reflecting real economics.

The current fresh-day state is `pending`, which is the correct fail-closed behavior while authoritative equity is invalid.

## This Week's Reliability / Architecture / Governance Changes

### 2026-08-18

- PR #79 merged: validate fresh cached quotes before `latest_price` return; exact poisoned-cache regression.
- PR #80 merged: fail closed on catastrophic persisted `last_price` valuation fallback.
- PR #81 merged: block duplicate full exits at the canonical pre-mutation boundary using the existing append-only ledger semantics; historical TEM evidence remains immutable.

### 2026-08-19

- PR #83 merged: prospective fresh-risk-day baseline sanity guard. Invalid/non-positive equity defers reset.
- Issue #84 opened: Stable Paper Core v3 architecture consolidation.
- PR #85 merged: Stage A immutable canonical shadow state models and ownership contract.

### 2026-08-20

- PR #86 merged: compact observational `/paper/fresh-day-check` endpoint.
- PR #87 merged: install fresh-day guard immediately after core `app` import and before full WSGI runtime composition; exact Gunicorn startup validation passed.
- PR #88 merged: `MASTER_SYSTEM_AUDIT_2026-08-20.md` plus architecture-debt regression gate.
  - 250 Python files / 90,409 lines at audit creation
  - 34 runtime mutation overlaps
  - 5 environment conflicts
  - 5 route overlaps
  - 80 duplicate-function groups
  - 540 broad exception-pass sites
  - 8 watchdog loops
  - 32 critical findings
  - fragmented ownership included `save_state` 17 owners, `scan_signals` 14, `try_entries_and_rotations` 13, `entry_quality_check` 10, `enter_position` 9
- PR #89 merged: Stage B deterministic shadow valuation service.
- PR #90 merged: Stage C deterministic shadow risk engine.
- PR #91 merged: Stage D shadow canonical StateStore with integrity hashing, atomic-write/backup/readback/restart invariants; no production I/O authority.
- PR #92 merged: Stage E shadow ledger-derived bidirectional accounting projection.

### 2026-08-21

- PR #93 merged: Stage F shadow canary-readiness planner; authoritative activation remains blocked by Issue #82.
- Issue #94 created for mandatory per-change regression/impact auditing.
- PR #95 merged: exact-head `Change Safety Audit` workflow/policy. Relevant future PRs must pass impact-aware regressions, core invariants, architecture/config/ownership/debt checks, and exact startup smoke; stale/missing/failing evidence blocks merge.
- Issue #96 created for self-diagnosing incident triage/recommendation.
- PR #97 merged: shadow-only `system_sentinel` foundation with deterministic incident classification and impact-aware test selection; no production state mutation or self-healing authority.
- PR #98 merged as `c6ef7958a247ae88ba9a5c3670ed756ac0d06426`: `entry_pipeline_xray` no longer loads/saves authoritative state or reassigns `core.portfolio`; regression reproduces stale-file/live-memory split and proves X-Ray does not replace live state.
- PR #98 passed Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit including exact Gunicorn startup smoke, and Change Safety Audit. Railway deployment succeeded.
- PR #99 merged as `0874368ad5bf303337b8c94ed1c9ae967c2231b5`: authoritative handoff refreshed through Aug 21. It was documentation-only and did not change runtime behavior.

## Stable Paper Core v3 / Issue #84

Issue #84 remains open. Shadow/parity status:
- Stage A — merged (#85): immutable canonical state models
- Stage B — merged (#89): deterministic valuation
- Stage C — merged (#90): deterministic risk lifecycle
- Stage D — merged (#91): shadow StateStore
- Stage E — merged (#92): ledger/accounting projection
- Stage F — merged (#93): canary readiness only; no authoritative activation
- Stage G — not accepted; legacy mutation wrappers cannot be removed until authoritative cutover and parity evidence are clean

Authoritative cutover remains blocked by Issue #82. Do not use the shadow core to bypass the current corrupted state.

## Mandatory Future Change Safety / Issue #94

PR #95 implemented the in-repository exact-head audit. Every relevant future PR must be reviewed against the exact PR head and pass the Change Safety Audit plus the required overlapping regressions/core invariants. A local unit test is not sufficient. Missing, stale, incomplete, or failing audit evidence is a merge blocker.

Final post-rebuild completion still includes repository-rule/branch-protection enforcement where permissions support it and acceptance/closure of Issue #94.

## Self-Diagnosing Sentinel / Issue #96

PR #97 provides the shadow diagnostic foundation. It can classify supplied evidence across valuation, accounting, execution ledger, risk, startup, configuration, ownership, runner, and market-data boundaries and select deterministic affected tests while retaining mandatory core tests.

It must not automatically rewrite portfolio/accounting/risk state, clear halts, alter execution history, change strategy/sizing/hard-risk/live/ML authority, or auto-merge authoritative fixes. Production advisory activation waits for stable canonical ownership.

## Prior Verified Accounting Recovery — Preserve as Forensic Evidence

The previously established recovery architecture created `stable-paper-v2-20260812-verified01` from a verified snapshot with an open LRCX lot and archived the prior contaminated epoch. Recovery code and forensic markers are evidence sources only; do not re-run the one-shot recovery blindly.

The active 2026-08-21 runtime no longer exposes that verified epoch. The canonical ledger reports `legacy-pre-stable-core`, and the clean-epoch status now also reports no active clean metadata or clean completion marker at the expected path. The next task is therefore provenance discovery, not account repair.

## Historical TEM Duplicate Exit

Historical TEM sequence remains immutable evidence:
1. entry long `29.640567 @ 54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`;
2. first full exit `29.640567 @ 53.105`, execution `7b13d9194a23407f926667b2f48d4057`;
3. duplicate full exit `@ 52.905`, execution `3530dbf965db4894ba93b7098cec3696`.

PR #81 prospectively blocks a future duplicate full exit before cash/P&L/position/ledger mutation. Never delete, rewrite, fabricate, or relabel the historical TEM row.

## Canonical Runtime / Validation Links

Use the clean service only:
- bootstrap: `https://trading-bot-clean.up.railway.app/bootstrap-status`
- compact fresh-day: `https://trading-bot-clean.up.railway.app/paper/fresh-day-check`
- fresh-day guard: `https://trading-bot-clean.up.railway.app/paper/fresh-risk-day-baseline-guard-status`
- routine self-check: `https://trading-bot-clean.up.railway.app/paper/self-check`
- targeted full diagnostics: `https://trading-bot-clean.up.railway.app/paper/full-self-check`
- routine daily audit: `https://trading-bot-clean.up.railway.app/paper/daily-audit`
- full daily audit: `https://trading-bot-clean.up.railway.app/paper/daily-audit?full=1`
- canonical ledger: `https://trading-bot-clean.up.railway.app/paper/canonical-execution-ledger-status`
- clean epoch status: `https://trading-bot-clean.up.railway.app/paper/clean-accounting-epoch-status`
- state recovery status: `https://trading-bot-clean.up.railway.app/paper/state-recovery-status`
- state I/O status: `https://trading-bot-clean.up.railway.app/paper/state-io-status`
- quote/exit integrity: `https://trading-bot-clean.up.railway.app/paper/exit-price-integrity-status`

Do not manually call `/paper/run` unless a specific future validation plan explicitly requires it.

Known ops debt: `.github/workflows/refactor-audit.yml` still contains the older hard-coded `https://web-production-e1796.up.railway.app` runtime-research target even though `runtime_research_snapshot.py` defaults to `trading-bot-clean`. Do not treat the old-domain automated snapshot as clean-service acceptance evidence.

## Risk / Authority Boundaries — Preserve

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`
- terminal-price plausibility: `0.40x` minimum / `2.50x` maximum
- paper-only until explicit live-readiness approval
- rules remain sole execution authority
- ML remains shadow-only for execution
- no fabricated/deleted/rewritten historical ledger rows
- no manual account-state repair merely to pass an audit

## Exact Next Action

The clean-epoch endpoint now proves the expected clean completion marker/archive pointer is absent from the active status path, while the canonical ledger remains healthy under `legacy-pre-stable-core`.

Continue with **read-mostly provenance**, not account mutation:

1. inspect `/paper/state-recovery-status` to determine whether `state_guard` restored any backup at startup and compare current-state quality versus the largest backup (`decision`, `restored`, current/backup trade counts, runner timestamp ranks, size/quality);
2. if a backup restoration occurred, identify which backup and whether that restoration predates the verified-snapshot epoch; do not restore another backup manually;
3. if no restoration occurred, add a bounded observational provenance probe that reads only exact recovery marker files and forensic archive manifests/directories, with no state write/restore/relabel authority, then validate it through the mandatory Change Safety Audit;
4. use that evidence to identify the earliest point at which `paper_accounting_epoch` / `accounting_epoch_id` disappeared and whether the pre-PR #98 X-Ray stale-file path is the exact source;
5. only after provenance is mechanically proven, design a bounded successor recovery that preserves all 55 canonical ledger rows/hash chain and all historical evidence;
6. after authoritative state is safely restored from proven evidence, require a new fresh-day reset from sane equity, then forward-session and clean-active-audit proof before closing Issue #82 or activating Stage F/G authority.

Do not use the incomplete `$10,724.779592` reconstruction as an automatic state repair.

## Conversation Continuity Protocol

Keep updates in the **current active project chat**, whichever ChatGPT conversation is presently designated for this project. If that conversation becomes too long for safe continuation, update this handoff with all material PR/commit/deployment/runtime evidence and the exact next action before moving. Then use the continuation command in the new conversation; the new conversation becomes the active project chat. Do not rely on an old monitoring thread for status.

Continuation command if required:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Treat this conversation as the current active project chat and keep project-status communication here. Verify current main/PR/CI and the canonical Railway clean-service read-only evidence before changing code. Continue from the Exact Next Action. Preserve paper-only authority, hard risk thresholds, canonical ledger history, rules-only execution authority, ML shadow-only execution, and the Issue #82/#84/#94/#96 gates. Do not manually repair account state or clear halts from inference.
```
