# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-10 13:06 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
GitHub main head covered: `6e7500a06935bc75a7f44d8ae742cd37b87bc5f6`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway deployment of the current GitHub head: **not yet verified from the current session**

This is the authoritative handoff for the next conversation. Older `PROJECT_HANDOFF_*` files are historical context unless this file explicitly references them.

## Executive Status

The project is in a **Stable Core + Performance Lab** phase.

The immediate objective is to establish a stable, operational paper/live-ready core while preserving the strategy/scanner components that previously produced useful participation and preserving future upside from ML, crypto, MAE/MFE, LONA, and shadow ranking.

The runtime remains **paper-only**. The rules engine remains the sole execution authority. ML and multi-asset ranking remain shadow/research-only and must not place orders, select or override entries/exits, change sizing, relax hard risk, change thresholds, or obtain live authority without an explicit later promotion decision.

The current paper account remains under a **hard risk halt** because of accounting/state contamination discovered on 2026-08-10. Do not clear the halt manually until the account is either reconstructed from trustworthy evidence or a clean accounting epoch is intentionally created.

## Operator Workflow — One Routine Test

The user wants **one routine test only** unless a demonstrated blocker requires a targeted diagnostic.

Routine test:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

Full forensic output only when necessary:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Do not make bootstrap + multiple accounting + multiple audit endpoints the normal workflow. The compact audit must remain short enough to copy/paste from iPhone.

After PR #24 is deployed, the compact audit should include both:

- `journal_recovery_candidate` — historical recovery evidence from the existing mirrored journal
- `execution_ledger` — health of the new canonical append-only ledger for **new** executions

## Current GitHub Head / Latest Change

PR #24 — **Add canonical execution ledger for Stable Core** — passed both repository CI workflows and was squash-merged into `main` as:

`6e7500a06935bc75a7f44d8ae742cd37b87bc5f6`

PR #24 adds:

- `canonical_execution_ledger.py`
- an append-only JSONL execution ledger on the persistent state volume
- a SHA-256 hash chain across execution rows
- a durable `execution_id` for every new `entry`, `exit`, and `partial_exit`
- accounting epoch id and ledger hash metadata propagated into the corresponding `state.trades` row
- direct wiring at the canonical `record_trade` boundary
- fail-safe hard-halt behavior if the canonical ledger cannot be written or its hash chain is invalid
- preservation of an already-active halt reason rather than overwriting it
- `/paper/canonical-execution-ledger-status`
- compact `execution_ledger` health inside `/paper/daily-audit`
- regression coverage for hash chaining, tamper detection, state-row linkage, fail-safe halting, and compact audit exposure
- startup bridge version `data-integrity-startup-bridge-2026-08-10-v11-canonical-execution-ledger`
- compact audit compactor version `final-daily-audit-compactor-2026-08-10-v2-canonical-ledger`

Important boundary: the canonical ledger is authoritative for **new executions after it is deployed and hooked**. It is deliberately **not** a fabricated historical recovery source and does not claim to reconstruct the contaminated pre-ledger account.

The two repository validation workflows passed before merge:

- Repository Safety and Performance Audit Validation
- Refactor, Ownership, Configuration, State, Decision, Runtime, Startup, and Research Audit

## Accounting Incident — Root Cause and Current Understanding

On 2026-08-10 the paper account began reporting economically impossible values, including very large negative cash and oversized positions. Symptoms included repeated apparent MARA purchases and an impossible QQQ cost basis.

### Defect 1 — side-first reconstruction

Canonical trade rows store `action` separately from `side`, for example:

- `action="exit"`
- `side="long"`

Older reconstruction treated `side="long"` as a buy before consulting `action`. Legitimate long exits were therefore reconstructed as additional buys, causing fake position growth, negative cash, and contaminated P&L/account state.

PR #21 corrected this by making **action authoritative**.

### Defect 2 — unmatched exits creating synthetic cash

Once action semantics were corrected, unmatched/duplicate exits could still credit proceeds even when no reconstructed lot existed.

PR #22 changed reconstruction so exit proceeds are credited only for quantity proven to exist in reconstructed lots.

### Remaining historical coverage problem

The latest captured pre-PR #23 audit showed:

- `state.trades`: **30 execution rows**
- unmatched exit/partial-exit rows: **19**
- `coverage_complete: false`

Therefore exact historical reconstruction from `state.trades` alone is impossible.

The bounded reconstructed candidate at that point was approximately:

- cash: `$14,386.33`
- equity: `$18,004.11`
- one reconstructed QQQ lot
- ignored/unmatched execution rows: `19`

Those values are **not trusted account values** because ledger coverage is incomplete.

## Historical Append-Only Journal Recovery Candidate

The bot has an older persistent mirrored journal at `/data/trade_journal.json` through `trade_journal.py`.

It:

- mirrors trade history from state and backup files
- does not shrink existing journal history
- maintains a backup journal
- seeds from state backups and current state
- does not write to `state.json`

PR #23 added `paper_journal_forensic_recovery.py`, which builds a **read-only semantic-deduplicated execution candidate** from that journal and analyzes it through the matched-exit accounting guard.

The routine audit reports whether this historical journal candidate is:

- available
- complete
- economically consistent
- a `trusted_recovery_candidate`

### Historical Recovery Decision Rule

1. If `journal_recovery_candidate.trusted_recovery_candidate == true`, use the journal as the evidence base for **one controlled state rebuild**.
2. If the journal candidate remains incomplete or economically inconsistent, **stop reverse-engineering contaminated history**.
3. Archive current state/journal/backups as forensic evidence and start a **clean accounting epoch** using the existing proven strategy logic.
4. Do not carry contaminated historical MAE/MFE promotion evidence into the new epoch.

This decision has **not** been made yet because the current session could not reach the deployed Railway audit endpoint to read the live candidate. Do not guess the answer from repository code alone.

## New Canonical Execution Ledger — Stable Core Foundation

PR #24 closes the forward-looking execution-history gap that allowed `state.trades` resets/truncation to become existential accounting problems.

For each new execution, the ledger records before the event is mirrored into the capped state trade list:

- `execution_id`
- ledger version
- local timestamp
- accounting epoch id
- action
- symbol
- side
- fill price
- shares
- execution metadata
- previous event hash
- event hash

The ledger is append-only and hash-chained. Existing rows are verified before a new row is appended.

If the ledger is unreadable, unparseable, hash-invalid, or unwritable, the runtime records the error in risk state and ensures a hard halt is active. An already-active halt and its reason are preserved.

The new ledger does **not**:

- clear the current accounting halt
- repair historical state
- place orders itself
- change scanner or strategy logic
- change thresholds
- change sizing
- loosen risk
- enable crypto execution
- grant live authority
- grant ML authority

Default epoch label before a deliberate clean/recovered epoch is established:

`legacy-pre-stable-core`

A future controlled recovery or clean-epoch action should establish an explicit new accounting epoch id so forward evidence is cleanly separable from contaminated history.

## PR History — Accounting / Stable Core Incident

### PR #20 — Harden paper ledger economics and block ORLA

Merged as `73e118a...`.

Added economic-ledger validation, cash overspend detection, negative reconstructed-cash detection, MAE/MFE promotion blocking while accounting is dirty, and ORLA static no-data/delisting hygiene.

### PR #21 — Recover paper ledger with action-first trade semantics

Merged as:

`60014694b829c2433e20bca32bd41920e7801095`

Made `action` authoritative and established a post-recovery MAE/MFE evidence epoch while preserving the hard halt.

### PR #22 — Prevent unmatched exits from creating synthetic paper cash

Merged as:

`ce51bb72c727147914371b0618dc714d4fcd335e`

Added matched-lot exit accounting and explicit incomplete-coverage failure.

### PR #23 — Make daily audit one-link compact and add journal recovery candidate

Merged as:

`8fcf06622759cc5775a23361c12de1087f73e4b7`

Added final response-stage compacting and the read-only historical journal recovery candidate.

### PR #24 — Add canonical execution ledger for Stable Core

Merged as:

`6e7500a06935bc75a7f44d8ae742cd37b87bc5f6`

Established the immutable source of truth for **new** execution events and exposed its health in the one-link audit.

## What We Know Works / Should Be Preserved

The stabilization audit indicates the largest failure cluster is **accounting/state reconstruction and overlapping runtime plumbing**, not the market-data/scanner side.

Preserve unless new evidence proves a specific defect:

- rules-engine execution authority
- broad-market momentum discovery
- canonical bounded detailed scanner
- scanner ownership / recursion-safety contract
- opening-surge and breakout participation logic that improves deployment without bypassing hard risk
- provider timeout/circuit/hygiene protections
- ORLA/static no-data hygiene
- persistent Railway volume
- cycle-completion contract
- hard risk system
- after-hours market-closed skipping
- paper-only execution boundary

### Risk boundaries to preserve initially

- soft daily-loss pause: `1.0%`
- hard realized-loss halt: `2.5%`
- hard intraday drawdown halt: `2.5%`
- absolute daily-loss ceiling: `3.0%`
- maximum account risk per trade at configured stop: `2.0%`

Do not loosen these merely to generate more trades or accelerate validation.

### Scanner / discovery architecture worth preserving

Historical handoff bounds:

- maximum retained discovery candidates: `160`
- maximum broad-momentum slots: `80`
- maximum base/fallback slots: `25`
- maximum detailed-scanner input: `110`
- discovery cache: `900` seconds

Provider/scanner infrastructure repeatedly showed healthy request accounting and clean operation during good runtime periods.

## Performance Evidence — Preserve the Engine, Not Corrupted P&L

There were earlier paper periods with strong positive account movement, including a remembered period from roughly `$10,000` to around `$11,000` in about a week.

Because historical accounting has now been proven incomplete/contaminated, do **not** treat all displayed historical P&L as audited evidence.

Preserve the strategy configuration, scanner behavior, participation logic, and risk architecture from stronger periods where they can be separated from accounting/runtime defects.

Principle:

**Simplify the plumbing, preserve the performance engine.**

## Stable Core + Performance Lab Architecture

### Stable Core

Production/paper authority should converge toward:

1. one canonical scanner/selection path
2. one execution pipeline
3. one immutable execution ledger — **forward foundation now added in PR #24**
4. one authoritative account/position state
5. execution-boundary cash/notional/position invariants
6. one risk controller
7. one persistence/backup contract
8. one compact daily audit

The next Stable Core engineering work, after the historical recovery-vs-clean-epoch decision, should focus on items 4–7 and reducing redundant execution-path wrappers.

### Performance Lab

Keep, but do not grant execution authority to:

- ML recommendation/counterfactual work
- MAE/MFE research and future stop/target optimization
- multi-asset shadow ranker
- BTC / ETH / SOL research
- LONA independent backtesting and robustness tests
- alternate regime/participation policies
- future walk-forward / Monte Carlo / stress testing

## ML / MAE-MFE Status

ML remains shadow-only.

The evidence-epoch guard requires new clean exact-lifecycle evidence after accounting truth is restored.

Latest captured pre-PR #23 state:

- valid exact-lifecycle rows: `3`
- post-recovery valid exact-lifecycle rows: `0`
- promotion evidence eligible: `false`
- promotion block: `post_accounting_recovery_forward_validation_required`

Old contaminated/recovery-era rows must not satisfy future ML promotion gates.

## Multi-Asset / Crypto Research

PR #19 added the shadow multi-asset ranking foundation, merged as `1892068...`.

It compares equities/ETFs with BTC, ETH, and SOL while remaining research-only.

No crypto execution until Stable Core is proven.

## LONA Status

LONA remains useful for independent validation. The last known limitation was a connector/backend schema mismatch for datasets with multiple frequencies: the backend required a timeframe/frequency while the exposed backtest action did not provide one.

Do not modify the trading bot merely to work around that connector limitation.

Use LONA later for independent backtesting, walk-forward validation, Monte Carlo analysis, slippage/commission stress, and Stable Core comparison when the connector interface supports it.

## Provider / Runtime Health Evidence

Before the accounting incident, runtime/provider infrastructure repeatedly demonstrated:

- provider request accounting reconciled
- no active recursion errors
- persistent state matched memory/disk
- after-hours cycles skipped correctly
- entry-pipeline ownership stable
- protected benchmark symbols not blocked
- provider circuit closed

The accounting incident is not evidence that scanner/provider/market-data logic is fundamentally broken.

## Known Operational Weaknesses

### 1. Historical accounting/state truth — primary blocker

`state.trades` is incomplete for the contaminated history. The older mirrored journal may or may not contain enough evidence; the live compact audit must decide that.

PR #24 prevents this same class of forward execution-history loss from depending solely on `state.trades`, but it cannot retroactively create missing historical entries.

### 2. Authoritative account/position state

After recovery or clean epoch, Stable Core still needs one explicit account/position authority derived consistently from the canonical execution ledger plus current marks.

### 3. Execution invariants

Add explicit execution-boundary invariants for cash, notional, lot ownership, position quantity, duplicate execution ids, and ledger/state synchronization.

### 4. Overlay accumulation

The runtime contains many historical overlays/wrappers. They were useful diagnostically but create startup complexity and ownership ambiguity.

Move important behavior into explicit canonical modules and remove/bypass redundant execution-path wrappers gradually, with regression gates.

### 5. Startup duration

Cold-start/runtime registration has often taken roughly 1–3+ minutes. Slow startup alone has not meant failure when heartbeat continues, but Stable Core should reduce this materially where possible.

### 6. Audit payload size

Addressed by PR #23 and extended carefully by PR #24. Routine audit must remain one-link and compact.

## Current Safety State

Until accounting truth is established:

- keep hard halt active
- do not manually reset cash, positions, P&L, or halt based on contaminated state
- do not trust historical reconstructed P&L as strategy evidence
- do not promote ML/MAE-MFE authority
- do not expand execution strategies
- do not enable crypto execution
- do not start live trading

## Revised Stabilization Strategy

Execution-authority feature freeze remains in force.

Allowed work:

- historical recovery or clean-epoch creation
- canonical ledger/account-state integration
- execution invariants
- state/persistence simplification
- startup simplification
- one-link audit reliability
- regression testing
- removal/bypass of redundant execution-path overlays

Not allowed until Stable Core is proven:

- new execution strategies
- crypto execution
- ML execution authority
- new sizing regimes
- threshold loosening for more trades
- speculative architecture additions

## Stable Paper v1 Acceptance Gate

After accounting truth is restored — by trusted recovery or clean epoch — run the **same Stable Core unchanged**.

Minimum acceptance target:

- `5` consecutive trading days
- no state corruption
- no impossible accounting
- no duplicate execution
- canonical execution hash chain remains valid
- every state execution maps to a canonical `execution_id`
- no unexplained startup failure
- no manual state repair
- one compact daily audit per day
- provider accounting clean
- cycle ownership clean
- risk controls behave as designed
- entry → fill → position → exit → immutable ledger consistency

A longer `7–10` day evidence window remains preferable if defects recur.

## Live-Readiness Direction

Desired sequence:

1. verify current GitHub head is deployed
2. determine trusted historical recovery vs clean epoch from one compact audit
3. establish accounting truth and an explicit clean accounting epoch id
4. finish authoritative account state + execution invariants + persistence contract
5. freeze Stable Core
6. complete at least 5 unchanged clean paper trading days
7. validate entry/exit/sizing/risk behavior from the canonical ledger
8. run live-readiness simulation against broker-state assumptions
9. move to a controlled live pilot at a funding level large enough to exercise the real architecture without forcing immediate redesign

Do **not** automatically default to an extremely small `$500` pilot if that would distort sizing, diversification, minimum-notional behavior, or transaction-cost assumptions. Determine minimum viable live capital from final Stable Core sizing rules.

## Immediate Priority Order for the Next Chat

1. Verify Railway deploys GitHub head `6e7500a06935bc75a7f44d8ae742cd37b87bc5f6` and startup bridge v11.
2. Run **only** the normal compact daily audit.
3. Confirm `execution_ledger` reports a healthy hook/hash chain and is authoritative for new executions.
4. Inspect `journal_recovery_candidate.trusted_recovery_candidate`.
5. If trusted: implement one controlled journal-based state rebuild with immutable forensic archive and halt preserved until the post-rebuild audit passes.
6. If not trusted: archive contaminated state/journal/backups and intentionally create a **clean accounting epoch** rather than continuing historical repair loops.
7. Establish an explicit accounting epoch id for all new canonical ledger rows.
8. Build authoritative account/position state and execution-boundary invariants around the canonical ledger.
9. Simplify persistence/risk ownership and remove redundant hot-path wrappers incrementally.
10. Preserve current rules/scanner performance logic unless evidence proves a specific component defective.
11. Keep ML/crypto/LONA/MAE-MFE in Performance Lab shadow mode.
12. Start the 5-day Stable Paper v1 clock only after accounting truth is clean.

## Tooling / Connected Services

Use GitHub/Codex tooling for code inspection, implementation, CI, regression review, and deployment work.

LONA is connected and may be used for independent research/backtesting when its frequency interface is usable.

Railway is the canonical deployment environment, but there is no direct Railway connector in the current toolset. Use deployed HTTP audit output and/or user-provided Railway status/logs for live verification.

## Important User Operating Preferences

- Prefer **one routine test link** per day.
- Avoid multiple diagnostics unless a specific failure requires them.
- Keep routine audit output short enough to copy/paste from iPhone.
- Prefer complete/codebase-level fixes over repeated manual patches.
- Prioritize reaching an operational live-ready system sooner rather than indefinite feature work.
- Do not sacrifice long-term performance ceiling or future ML capability merely to simplify the current runtime.

## Non-Negotiable Boundaries

- Paper-only until explicit live-readiness approval.
- Existing hard halt remains until trustworthy accounting/state is established.
- Rules engine remains sole execution authority.
- ML remains shadow-only.
- Multi-asset ranker remains research-only.
- No risk-threshold weakening merely to create trades.
- No fabricated ledger rows or synthetic historical entries.
- No automatic clearing of halt during accounting recovery.
- Preserve forensic state/backups before any destructive clean-epoch action.
- The new canonical execution ledger is authoritative only for executions actually recorded through it; do not use it to invent pre-deployment history.

## Continuation Prompt for New Chat

A new chat should begin by reviewing this file, confirming the latest GitHub `main` head, and then using only the normal Railway compact audit.

The two immediate questions are:

1. **Is PR #24 deployed and is `execution_ledger` healthy/authoritative for new executions?**
2. **Does `journal_recovery_candidate.trusted_recovery_candidate` provide complete, economically consistent historical coverage?**

If the journal candidate is trusted, perform a controlled recovery. If it is not trusted, start a clean accounting epoch and move immediately into Stable Core validation rather than continuing to patch contaminated history.
