# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-13 after PR #56 source-quote review  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Canonical Railway paper service: `https://web-production-e1796.up.railway.app`

This file is the authoritative continuation point. Older `PROJECT_HANDOFF_*` files are historical context only unless this file explicitly references them.

## Executive Status

The project is in **Stable Core repair/validation + Performance Lab shadow** mode.

Runtime remains **paper-only**. Rules remain the sole execution authority. Live authority is disabled. ML/AI, MAE/MFE optimization, crypto/multi-asset ranking, LONA, adaptive policies, and other research systems remain shadow/research-only unless an explicit later promotion decision is made.

The correct architectural direction remains: preserve the performance engine, simplify ownership/runtime plumbing, and avoid broad wrapper-style repairs when a narrow correctness fix is available.

## Canonical Service / State

Use only this Railway service for the Stable Paper runtime:

`https://web-production-e1796.up.railway.app`

Do **not** use `trading-bot-clean.up.railway.app` for validation. It was proven to be attached to a different stale/legacy persistent state lineage (`/data/state.json`) and produced invalid accounting/risk state.

The canonical service uses `/app/data/state.json` and carries the verified Stable Paper v2 state.

## Current Accounting Epoch — Authoritative

Current epoch:

`stable-paper-v2-20260812-verified01`

Prior epoch:

`stable-paper-v1-20260810-clean01`

Current baseline type:

`verified_snapshot_with_open_position`

Historical recovery decision:

`verified_snapshot_rollforward`

Why v2 exists: independent evidence proved the catastrophic LRCX paper exit near `$36.26` was a bad tick. The legitimate remaining LRCX lot therefore could not honestly be discarded as if the account had a zero-position clean baseline.

Verified v2 starting state:

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
- ledger epoch must equal `stable-paper-v2-20260812-verified01`
- every new state execution must map to a canonical `execution_id`
- no fabricated rows

## Routine Operator Test

Use this one routine test:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

For targeted forensic detail only when the routine audit identifies a blocker:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Useful targeted diagnostics currently include:

- `/paper/runtime-errors`
- `/paper/exit-price-integrity-status`
- `/paper/state-persistence-contract-status`
- `/bootstrap-status`

Do not manually run `/paper/run` unless a future explicit validation plan requires it.

## PR #54 — Verified-Snapshot Accounting Concurrency Fix

Production traceback proved an automatic cycle could fail with:

`RuntimeError: dictionary changed size during iteration`

Exact boundary:

`verified_snapshot_accounting_baseline.py` called `copy.deepcopy(pf)` while unrelated live telemetry dictionaries were being mutated by another runtime thread.

The accepted fix was surgical: preserve the original verified-snapshot accounting adapter and replace only the whole-portfolio deepcopy with a detached accounting-only working view containing the fields required by the bidirectional accounting analyzer.

Final runtime-file diff on PR #54 was only 9 additions / 2 deletions, plus focused regression coverage. Both authoritative CI workflows passed.

Post-deploy evidence on 2026-08-13 showed:

- runner `active_error: false`
- automatic cycles completing successfully
- accounting coverage complete
- zero accounting/economic issues
- canonical v2 epoch aligned

`last_error` may still display the historical dictionary error as telemetry, but it is not active when `active_error: false` and a later successful run exists.

## Current 2026-08-13 Post-Deploy Account Evidence

Latest compact audit supplied after PR #54 deployment:

- cash: approximately `$7,836.229902`
- equity: approximately `$15,091.64`
- positions: `LRCX`, `QQQ`, `UCTT`, `TEM`
- realized today: approximately `$1,403.75`
- unrealized P&L: approximately `$1,847.75`
- accounting coverage complete: `true`
- coverage issues: `0`
- economic issues: `0`
- parsed post-v2 trade rows: `4`
- reconstructed positions match runtime positions
- canonical ledger chain valid
- canonical current epoch rows: `8`

Forward evidence has now produced at least one valid post-recovery exact lifecycle row. `promotion_evidence_eligible: true` does **not** grant ML execution authority; ML remains shadow-only.

## Active Blocker — Paper Exit Quote Integrity Halt

The current runtime blocker is **not** the prior dictionary concurrency failure.

Active risk state:

- `halted: true`
- `self_defense_active: true`
- halt reason: `paper exit quote integrity halt`

The quote-integrity guard captured this exact blocked exit attempt:

- symbol: `LRCX`
- boundary: `exit_position`
- verified entry: `$312.90`
- attempted exit price: `$18.401199340820312`
- price/entry ratio: approximately `0.05881`
- reason: `catastrophic_long_exit_price_outlier`

The guard is fail-closed and behaved correctly. It must **not** be weakened or bypassed merely to resume trading.

Root tracing established that `app.latest_price()` trusts the terminal yfinance 5-minute `Close`, caches it for 60 seconds, and position management then writes that price into the open position before exit evaluation. The existing market-data resilience layer sanitizes requests, disables threaded yfinance downloads, and handles timeout/backoff/provider-circuit behavior, but it does not validate a successful terminal bar for price plausibility.

Do not clear the current quote-integrity halt until the source is contained and post-deploy evidence confirms containment.

## PR #56 — Source Quote Plausibility Containment — HOLD

PR #56: `Reject catastrophic terminal quotes before latest-price cache`

Branch:

`fix-source-quote-plausibility-20260813`

Current reviewed head before required correction:

`890227d40db5fcb317ec4e563089e2e34d60faaa`

Scope is intentionally narrow: extend `paper_exit_price_integrity_guard.py` with a paper-only source-level `latest_price` plausibility boundary and focused regression coverage. It does not rewrite `market_data_resilience.py`, alter account state, clear the persisted halt, change strategy/risk/sizing, or grant live/ML authority.

Both authoritative GitHub CI workflows passed on that head:

- `Repository Safety and Performance Audit Validation`: success
- `Refactor, Ownership, Configuration, State, Decision, Runtime, Startup, and Research Audit`: success

**Do not merge PR #56 yet despite green CI.** Manual review found a startup-order ownership hazard not covered by the current tests:

- `_wrap_latest_price` captures `core.download_prices` once at guard installation time.
- `market_data_resilience` is installed/reinstalled through `usercustomize` and its watchdog.
- `paper_exit_price_integrity_guard` is applied through `data_integrity_startup_bridge` on a separate startup path.
- Depending on registration timing, the captured function can be the pre-resilience `download_prices` implementation, so later fresh-price requests could bypass provider timeout/backoff/hygiene protections even though `core.download_prices` is subsequently wrapped correctly.

Required surgical correction before merge:

1. Do not capture `download_prices` outside the `latest_price` wrapper.
2. At each fresh fetch, resolve the current `download = getattr(core, "download_prices", None)` and require it to be callable.
3. Call that current owner so market-data resilience remains authoritative regardless of startup order.
4. Add/adjust a focused regression test proving that if `core.download_prices` is replaced after quote-guard installation, `latest_price()` uses the replacement/current callable rather than the earlier one.
5. Preserve the existing 60-second cache, source-plausibility thresholds, exit guard, account state, paper-only boundary, strategy/risk/sizing behavior, and live/ML authority.
6. Rerun both authoritative CI workflows after the correction.

A PR conversation hold comment documents this exact requirement. The connected GitHub safety layer blocked a direct runtime-code edit during the automated review, so no unsafe bypass was attempted and no merge occurred.

## Risk Boundaries — Preserve

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum configured account risk per trade at stop: `2.0%`

Do not weaken risk controls to create trades or accelerate validation.

The paper exit quote-integrity guard currently blocks long exit prices at or below 40% of entry and short exit prices at or above 2.5x entry. Treat it as a safety boundary unless later evidence proves the guard itself is incorrect.

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

Keep PR #56 unmerged. Correct the startup-order ownership hazard so source-level `latest_price` plausibility validation dynamically calls the current `core.download_prices` owner rather than a captured pre-resilience reference. Add the focused replacement-owner regression test, rerun both authoritative CI workflows, then review the exact diff again. Only after that correction is green may PR #56 be merged/deployed. After deploy, verify the canonical `/paper/daily-audit` and `/paper/exit-price-integrity-status` confirm source plausibility is installed and the bad LRCX quote cannot reach the exit boundary before considering any halt release.
