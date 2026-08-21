# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-21 10:05 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Current `main`: `c6ef7958a247ae88ba9a5c3670ed756ac0d06426` (`Prevent diagnostic X-Ray from replacing fresh paper state (#98)`)  
Canonical Railway paper service: `https://trading-bot-clean.up.railway.app`

## Communication / Continuity Rule

Keep Trading-bot progress updates in the active ChatGPT project conversation only. Do not surface project-status updates through separate ChatGPT monitoring conversations. On 2026-08-21 the project-specific `Trading System Completion` and `QQQ Repair Watch` monitoring tasks were disabled; `Trading Architecture Builder` was already disabled. Repository handoff maintenance remains required so a future conversation can recover exact state if continuity becomes necessary.

## Executive Status

Operational stabilization is still blocked by GitHub Issue #82. Runtime remains paper-only. Rules remain the sole execution authority. Live authority is disabled. ML/AI remains shadow-only for execution.

The fresh-day protection itself is now behaving fail-closed, but the active authoritative paper account snapshot is corrupted and cannot seed a new risk day. The current live/on-disk snapshot reports approximately `cash=-26064.308325`, `equity=-26064.31`, no open positions, and `realized_total=-94929.16`. The current risk state remains the stale 2026-08-20 state with `day_start_equity=-26064.31`, `day_peak_equity=0.01`, `halted=true`, `halt_reason='daily loss limit hit (3.0%)'`, and `fresh_day_reset_pending=true`.

Do not clear the halt, rewrite the risk peak, force a fresh-day baseline, or overwrite the account from a reconstructed balance merely to make the audit pass.

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

Interpretation: the guard is doing its job. It is refusing to manufacture a new 2026-08-21 risk baseline from invalid active equity.

### Compact self-check

`/paper/self-check` at `2026-08-21 09:51:12 CDT`:
- overall `warn`, HTTP/status contract `ok`
- account: cash `-26064.308324919723`, equity `-26064.31`, positions `[]`, realized today `0.0`, realized total `-94929.16`, unrealized `0.0`
- auto runner enabled and observed active; no active runner error
- all 9 bounded runtime component checks pass
- scanner/entry composition ownership checks pass
- runtime shadow capture parity passes
- risk remains halted/self-defense-active only because of the stale daily-loss halt state

### Full daily audit

`/paper/daily-audit?full=1` at `2026-08-21 09:52:32 CDT`:
- overall `fail` because risk remains halted and accounting integrity is not reconciled
- runner liveness passes; no active recursion/runtime error
- market-data/provider accounting is complete and clean at snapshot
- persistent volume is healthy; `/data/state.json` exists; in-memory/on-disk richness match; no recovery failure or detected state-file corruption
- therefore PR #98 appears to have stopped the diagnostic X-Ray overwrite path, but the state being faithfully persisted is already the contaminated state
- paper accounting reconstruction reports approximately `cash/equity=10724.779592`, `realized_total=724.779592`, zero positions, but coverage is incomplete with 193 ignored/unmatched exit rows, mostly legacy rows beginning on 2026-08-07
- because coverage is incomplete, **do not promote or write `$10,724.779592` into authoritative state**
- separate paper-ledger economic integrity also fails; the reconstructed number is evidence, not yet trusted recovery authority

### Canonical execution ledger

`/paper/canonical-execution-ledger-status` after PR #98:
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

This is the current decisive provenance finding: the active portfolio no longer exposes the verified `stable-paper-v2-20260812-verified01` accounting epoch, and all 55 surviving canonical rows are presently counted under `legacy-pre-stable-core`. The append-only chain itself is healthy. Do not relabel or rewrite these rows. Next recovery work must establish how the verified-snapshot epoch identity was lost/resurrected and use preserved recovery/forensic evidence rather than guessing.

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
4. clean active audit: sane valuation, healthy runner/market data, valid canonical chain, no new active coverage/economic issue, and risk reflecting real economics.

The current fresh-day result is `pending`, not accepted. That is the correct fail-closed state while active equity remains invalid.

## This Week's Reliability / Safety Changes

### 2026-08-18

- PR #79 merged: validate fresh cached quotes before `latest_price` return. Exact QQQ poisoned-cache regression; no strategy/risk/sizing authority change.
- PR #80 merged: fail closed on catastrophic persisted equity marks so a poisoned stored `last_price` cannot bypass protected quote retrieval.
- PR #81 merged: block duplicate full exits at the canonical pre-mutation boundary using the existing append-only ledger semantics; historical TEM evidence remains immutable.

### 2026-08-19

- PR #83 merged: prospective fresh-risk-day baseline guard. Invalid/non-positive equity defers reset instead of becoming the new day's baseline.
- Issue #84 opened: Stable Paper Core v3 architectural consolidation.
- PR #85 merged: Stage A immutable canonical shadow state models and ownership contract.

### 2026-08-20

- PR #86 merged: compact observational `/paper/fresh-day-check` endpoint.
- PR #87 merged: install fresh-day guard immediately after core `app` import and before full WSGI runtime composition; exact Gunicorn startup validation passed.
- PR #88 merged: `MASTER_SYSTEM_AUDIT_2026-08-20.md` plus architecture-debt regression gate.
  - latest audited source scale at creation: 250 Python files / 90,409 lines
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
- PR #91 merged: Stage D shadow canonical StateStore with integrity hashing, atomic writes, backup/readback/restart invariants; production I/O still disabled.
- PR #92 merged: Stage E shadow ledger-derived bidirectional accounting projection.

### 2026-08-21

- PR #93 merged: Stage F shadow canary readiness planner. Authoritative canary activation remains blocked by Issue #82.
- Issue #94 created for mandatory per-change regression/impact auditing.
- PR #95 merged: exact-head `Change Safety Audit` workflow and policy. It classifies change surface, selects impact-aware regressions, always retains core canonical invariants, runs architecture/config/ownership/debt/startup checks, and fails closed on stale/missing/failing evidence. Issue #94 remains open until final post-rebuild enforcement/branch-protection acceptance is complete.
- Issue #96 created for a self-diagnosing incident triage/recommendation engine.
- PR #97 merged: shadow-only `system_sentinel` with deterministic incident classification and impact-aware test selection. It has no production state authority and no self-healing enabled. Issue #96 remains open until production advisory activation after stabilization/rebuild acceptance.
- PR #98 merged to current main `c6ef7958a247ae88ba9a5c3670ed756ac0d06426`: diagnostic `entry_pipeline_xray` no longer loads/saves authoritative state or reassigns `core.portfolio`. Regression reproduces stale-file/live-memory split and proves no X-Ray state replacement.
- PR #98 head passed Repository Safety and Performance Audit Validation, Architecture Debt Regression Gate, Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research Audit including exact Gunicorn startup smoke, and Change Safety Audit. Railway deployment status on the merged main commit reported success.

## Stable Paper Core v3 / Issue #84

Issue #84 remains open. Shadow/parity implementation status:
- Stage A — merged (#85): immutable canonical state models
- Stage B — merged (#89): deterministic valuation
- Stage C — merged (#90): deterministic risk lifecycle
- Stage D — merged (#91): shadow StateStore
- Stage E — merged (#92): ledger/accounting projection
- Stage F — merged (#93): canary readiness only; no authoritative activation
- Stage G — not started/accepted; legacy mutation wrappers cannot be removed until authoritative cutover and parity evidence are clean

Authoritative cutover remains blocked by Issue #82. Do not promote the shadow core merely to bypass the current corrupted state.

## Mandatory Future Change Safety / Issue #94

PR #95 has implemented the in-repository mandatory exact-head audit. Every relevant future PR must be reviewed against the exact PR head and must pass the Change Safety Audit plus required overlapping regressions/core invariants. A local unit test is never sufficient by itself. Missing, stale, incomplete, or failing audit evidence is a merge blocker.

Final post-rebuild completion still includes repository-rule/branch-protection enforcement where permissions support it and final acceptance/closure of Issue #94.

## Self-Diagnosing Sentinel / Issue #96

PR #97 provides the shadow diagnostic foundation. It can classify supplied evidence across valuation, accounting, execution ledger, risk, startup, configuration, architecture ownership, runner, and market-data boundaries and select deterministic affected tests while retaining mandatory core tests.

It must not automatically rewrite portfolio/accounting/risk state, clear halts, alter execution history, change strategy/sizing/hard-risk/live/ML authority, or auto-merge authoritative fixes. Production advisory activation waits for stable canonical ownership.

## Prior Verified Accounting Recovery — Preserve as Forensic Evidence

The previously established recovery architecture created `stable-paper-v2-20260812-verified01` from a verified snapshot with an open LRCX lot and archived the prior contaminated epoch. Recovery code/forensic markers must be treated as evidence sources, not re-run blindly.

The active 2026-08-21 runtime no longer exposes that verified epoch and the canonical ledger reports `legacy-pre-stable-core`. This discrepancy is now the next provenance investigation. Do not assume the verified epoch can simply be restored from the reconstructed `$10,724.779592` value, and do not rewrite current canonical rows to a different epoch id.

## Historical TEM Duplicate Exit

Historical TEM sequence remains immutable evidence:
1. entry long `29.640567 @ 54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`;
2. first full exit `29.640567 @ 53.105`, execution `7b13d9194a23407f926667b2f48d4057`;
3. duplicate full exit `@ 52.905`, execution `3530dbf965db4894ba93b7098cec3696`.

PR #81 prospectively blocks a future duplicate full exit before cash/P&L/position/ledger mutation. Never delete, rewrite, fabricate, or relabel the historical TEM row to make accounting pass.

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
- quote/exit integrity: `https://trading-bot-clean.up.railway.app/paper/exit-price-integrity-status`

Do not manually call `/paper/run` unless a specific future validation plan explicitly requires it.

Known ops debt: `.github/workflows/refactor-audit.yml` still contains an older hard-coded `https://web-production-e1796.up.railway.app` runtime-research target even though `runtime_research_snapshot.py` defaults to `trading-bot-clean`. Do not treat that old-domain automated snapshot as clean-service acceptance evidence. Correct this metadata drift as governance/ops cleanup without mixing it into the current accounting recovery unless necessary.

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

The canonical ledger chain is healthy, but all 55 rows are currently associated with `legacy-pre-stable-core`, proving the active verified epoch identity is missing. Continue read-only provenance work before any account/state mutation:

1. inspect the clean-accounting and verified-snapshot recovery markers/status and archived successor evidence to determine whether the durable `stable-paper-v2-20260812-verified01` recovery completion evidence still exists;
2. compare that evidence with the 55 canonical rows and their recorded epoch ids without editing them;
3. establish the earliest point at which the active state lost `paper_accounting_epoch` / `accounting_epoch_id` and whether the stale snapshot resurrected by the pre-PR #98 X-Ray path is the exact source;
4. only after provenance is mechanically proven, design a bounded recovery/successor epoch that preserves the 55-row hash chain and all historical evidence, then run the mandatory Change Safety Audit before any merge/deploy;
5. after a safe authoritative state source is restored, require a new fresh-day reset from sane equity, then forward-session and clean-audit proof before closing Issue #82 or activating Stage F/G authority.

Do not use the incomplete `$10,724.779592` reconstruction as an automatic state repair.

## Conversation Continuity Protocol

Keep updates in the active project chat. If the active conversation becomes too long for safe continuation, first update this handoff with all material PR/commit/deployment/runtime evidence and the exact next action, then provide one continuation command. Do not rely on a separate monitoring chat for project status.

Continuation command if ever required:

```text
Use the direct @GitHub connector and continue the Trading-bot project from sterlingfancher-cmyk/Trading-bot. Read PROJECT_HANDOFF_CURRENT.md first and treat it as the authoritative continuation state. Keep all project updates in this chat only. Verify current main/PR/CI and the canonical Railway clean-service read-only evidence before changing code. Continue from the Exact Next Action. Preserve paper-only authority, hard risk thresholds, canonical ledger history, rules-only execution authority, ML shadow-only execution, and the Issue #82/#84/#94/#96 gates. Do not manually repair account state or clear halts from inference.
```
