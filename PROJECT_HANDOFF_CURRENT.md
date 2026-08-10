# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-10 12:51 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Runtime code head covered: `8fcf06622759cc5775a23361c12de1087f73e4b7`  
Canonical paper service: `https://web-production-e1796.up.railway.app`

This is the authoritative handoff for the next conversation. Older `PROJECT_HANDOFF_*` files are historical context unless this file explicitly references them.

## Executive Status

The project is now in a **Stable Core + Performance Lab** phase.

The goal is no longer to keep layering features onto the current runtime. The immediate priority is to produce a stable, operational paper/live-ready core without sacrificing the strategy components that have shown useful performance or the future upside from ML, crypto, MAE/MFE, LONA research, and shadow ranking.

The runtime remains **paper-only**. The rules engine remains the sole execution authority. ML and multi-asset ranking remain shadow/research-only and must not place orders, select or override entries/exits, change sizing, relax hard risk, change thresholds, or obtain live authority without an explicit later promotion decision.

The current paper account is still under a **hard risk halt** due to accounting/state contamination discovered on 2026-08-10. Do not clear the halt manually until the account state is either successfully reconstructed from trustworthy evidence or a clean accounting epoch is intentionally started.

## Operator Workflow — One Routine Test

The user has repeatedly requested **one routine test only** unless a deeper diagnostic is specifically necessary.

Routine test:

`https://web-production-e1796.up.railway.app/paper/daily-audit`

The default response must remain compact and copy/paste friendly. Full forensic output is available only when specifically needed:

`https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`

Do not ask the user to run bootstrap + multiple accounting + multiple audit endpoints as a normal workflow. Use the single compact audit whenever possible and add targeted diagnostics only for a demonstrated blocker.

PR #23 adds a final Flask response-stage compactor so later overlays cannot re-expand the routine audit.

## Current Runtime Head / Latest Change

PR #23 — **Make daily audit one-link compact and add journal recovery candidate** — passed both repository CI workflows and was squash-merged into `main` as:

`8fcf06622759cc5775a23361c12de1087f73e4b7`

It adds:

- `final_daily_audit_compactor.py`
- `paper_journal_forensic_recovery.py`
- startup bridge version `data-integrity-startup-bridge-2026-08-10-v10-one-link-journal-recovery`
- regression coverage for compact output and semantic journal deduplication

The forensic recovery candidate is **read-only**. It does not repair state, clear the halt, place orders, or change strategy/risk/sizing/live/ML authority.

## Accounting Incident — Root Cause and Current Understanding

On 2026-08-10 the paper account began reporting economically impossible values, including very large negative cash and oversized positions. Initial symptoms included repeated apparent MARA purchases and an impossible QQQ cost basis.

The first major root cause was identified in the trade parser:

- canonical trade rows store `action` separately from `side`
- examples: `action="exit"`, `side="long"`
- older accounting reconstruction treated `side="long"` as a buy before consulting `action`
- legitimate long exits were therefore reconstructed as additional buys

That created cascading fake position growth, negative cash, and contaminated P&L/account state.

PR #21 corrected this by making **action authoritative**.

A second defect was then exposed: unmatched or duplicate exits could create synthetic cash during reconstruction. PR #22 corrected this so exit proceeds are credited only for quantity proven to exist in reconstructed lots.

The remaining issue is now clearer and more fundamental:

- `state.trades` contains **30 execution rows** in the latest captured audit
- **19 exit/partial-exit rows have no matching entry lots available in `state.trades`**
- therefore exact account reconstruction from `state.trades` alone is impossible
- the matched-exit guard now correctly reports `coverage_complete: false`
- it no longer fabricates cash from those unmatched exits

The last single audit before PR #23 showed a bounded reconstructed candidate around:

- reconstructed cash: approximately `$14,386.33`
- reconstructed equity: approximately `$18,004.11`
- one reconstructed QQQ lot remained
- ignored/unmatched execution rows: `19`
- economic/accounting integrity: fail due incomplete ledger coverage

These values are **not yet trusted account values** because coverage is incomplete.

## Append-Only Trade Journal Recovery Candidate

The bot already maintains a separate persistent append-only trade journal at `/data/trade_journal.json` through `trade_journal.py`.

Important properties:

- mirrors trade history from state and backup files
- does not shrink existing journal history
- maintains a backup journal
- seeds from state backups and current state
- does not write to `state.json`
- was designed specifically to preserve execution history across state resets/redeployments

PR #23 now builds a **read-only deduplicated execution candidate** from this journal and runs it through the corrected matched-exit accounting guard.

The compact daily audit will report whether this journal candidate is:

- available
- complete
- economically consistent
- a `trusted_recovery_candidate`

### Recovery Decision Rule

1. If the journal candidate has complete entry/exit coverage and no economic issues, use it as the evidence base for a controlled state rebuild.
2. If the journal candidate is still incomplete, **stop spending time reverse-engineering contaminated history**.
3. Archive the current state/journal/backups as forensic evidence and start a **clean accounting epoch** using the existing proven strategy logic.
4. Do not carry contaminated historical MAE/MFE promotion evidence into the new epoch.

This decision rule is intended to prevent another prolonged historical repair loop.

## PR History — Accounting / Recovery Incident

### PR #20 — Harden paper ledger economics and block ORLA

Merged as `73e118a...`.

Added:

- economic-ledger validator
- detection of buys exceeding cash
- negative reconstructed cash detection
- MAE/MFE promotion block when accounting integrity is not clean
- ORLA static no-data/delisting hygiene block

This correctly exposed the impossible paper ledger instead of allowing a false green accounting result.

### PR #21 — Recover paper ledger with action-first trade semantics

Merged as:

`60014694b829c2433e20bca32bd41920e7801095`

Corrected the core semantic bug where exits from long positions were being reconstructed as buys.

Also established a post-recovery MAE/MFE evidence epoch and preserved the hard halt.

### PR #22 — Prevent unmatched exits from creating synthetic paper cash

Merged as:

`ce51bb72c727147914371b0618dc714d4fcd335e`

Added matched-lot exit accounting and made incomplete coverage an explicit integrity failure.

### PR #23 — Make daily audit one-link compact and add journal recovery candidate

Merged as:

`8fcf06622759cc5775a23361c12de1087f73e4b7`

This is the current `main` head covered by this handoff.

## What We Know Works / Should Be Preserved

The stabilization audit concluded that the largest failure cluster is **accounting/state reconstruction and overlapping runtime plumbing**, not the market-data/scanner side.

Preserve these components unless new evidence proves otherwise:

### Stable Core candidates

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

Do not loosen these merely to generate more trades or speed validation.

### Scanner / discovery architecture worth preserving

Historical handoff bounds:

- maximum retained discovery candidates: `160`
- maximum broad-momentum slots: `80`
- maximum base/fallback slots: `25`
- maximum detailed-scanner input: `110`
- discovery cache: `900` seconds

The scanner/provider layer has repeatedly shown healthy request accounting and clean provider operation during good runtime periods.

## Performance Evidence to Preserve — But Treat Carefully

The user recalls an earlier paper period roughly a month into development where the account increased from about `$10,000` to around `$11,000` within roughly a week.

Later captured paper results also showed periods of strong positive account movement. However, because the historical account ledger has now been proven incomplete/contaminated, **do not treat all displayed historical P&L as audited performance evidence**.

What should be preserved is the **strategy configuration and scanner behavior from the stronger periods**, not the corrupted account balances themselves.

The next architecture should attempt to retain those strategy components while simplifying the plumbing around them.

## Stable Core + Performance Lab Architecture

### Stable Core

Production/paper authority should converge toward only:

1. one canonical scanner/selection path
2. one execution pipeline
3. one immutable execution ledger
4. one authoritative account/position state
5. execution-boundary cash/notional/position invariants
6. one risk controller
7. one persistence/backup contract
8. one compact daily audit

The Stable Core should not depend on experimental ML, crypto, MAE/MFE optimization, or alternative research policies to execute trades.

### Performance Lab

Keep — do not delete — the following as shadow/research systems:

- ML recommendation/counterfactual work
- MAE/MFE research and future stop/target optimization
- multi-asset shadow ranker
- BTC / ETH / SOL research
- LONA independent backtesting and robustness tests
- alternate regime/participation policies
- future walk-forward / Monte Carlo / stress testing

These systems may score, compare, and record what they would have done, but must not mutate live/paper execution authority until promotion gates are satisfied.

## ML / MAE-MFE Status

ML remains shadow-only.

The current evidence epoch guard requires **new clean post-recovery exact-lifecycle evidence** before MAE/MFE-derived evidence can become promotable again.

The latest captured audit before PR #23 showed:

- valid exact-lifecycle rows: `3`
- post-recovery valid exact-lifecycle rows: `0`
- promotion evidence eligible: `false`
- promotion block: `post_accounting_recovery_forward_validation_required`

Do not allow old contaminated/recovery-era rows to satisfy future ML promotion gates.

## Multi-Asset / Crypto Research

PR #19 added the shadow multi-asset ranking foundation and was merged as `1892068...`.

It compares equities/ETFs with BTC, ETH, and SOL while remaining research-only.

It has no execution authority and must remain outside the Stable Core hot path until the base system is stable.

## LONA Status

LONA remains useful for independent validation, but the connector currently has a backend/schema mismatch for datasets that contain multiple frequencies: the backend requires a frequency/timeframe, while the exposed backtest action did not provide a frequency parameter during the last attempt.

Do not modify the trading bot merely to work around that connector limitation.

Use LONA later for independent backtesting, walk-forward validation, Monte Carlo analysis, slippage/commission stress, and comparison against the Stable Core when the connector path supports it.

## Provider / Runtime Health Evidence

Before the accounting incident, provider and runtime infrastructure repeatedly demonstrated healthy behavior:

- provider request accounting reconciled
- no active recursion errors
- persistent state matched memory/disk
- after-hours cycles skipped correctly
- entry pipeline ownership was stable
- protected benchmark symbols were not blocked
- provider circuit remained closed

The accounting incident should therefore not be interpreted as proof that scanner/provider/market-data logic is fundamentally broken.

## Known Operational Weaknesses

### 1. Accounting/state truth

Primary current blocker.

`state.trades` is not a sufficient immutable execution source of truth.

### 2. Overlay accumulation

The runtime currently contains many historical overlays and wrappers. They were useful for diagnosis but create startup complexity and ownership ambiguity.

The medium-term refactor should move important behavior into explicit canonical modules and remove redundant wrappers from the execution hot path.

### 3. Startup duration

Cold-start/runtime registration has often taken roughly 1–3+ minutes. Slow startup alone has not meant failure when heartbeat continues, but Stable Core should reduce this materially if possible.

### 4. Audit payload size

Addressed by PR #23. Routine audit must remain one-link and compact.

## Current Safety State

Until accounting recovery is proven:

- keep hard halt active
- do not manually reset cash, positions, P&L, or halt based on contaminated state
- do not trust historical reconstructed P&L as strategy evidence
- do not promote ML/MAE-MFE authority
- do not expand execution features
- do not start live trading

## Revised Stabilization Strategy

Feature freeze for execution authority.

Allowed work:

- canonical ledger/accounting repair or clean-epoch creation
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

After accounting truth is restored — either by trusted recovery or a clean epoch — run the **same Stable Core unchanged**.

Minimum acceptance target:

- `5` consecutive trading days
- no state corruption
- no impossible accounting
- no duplicate execution
- no unexplained startup failure
- no manual state repair
- one compact daily audit per day
- provider accounting clean
- cycle ownership clean
- risk controls behave as designed
- entry → fill → position → exit → immutable ledger consistency

A longer `7–10` day evidence window remains preferable if defects recur.

## Live-Readiness Direction

The previous long calendar-based roadmap is now secondary to a shorter evidence-gated path.

Desired sequence:

1. establish accounting truth / clean epoch
2. freeze Stable Core
3. complete at least 5 unchanged clean paper trading days
4. validate actual entry/exit/sizing/risk behavior from the canonical ledger
5. run live-readiness simulation against broker-state assumptions
6. move to a controlled live pilot at a funding level large enough to exercise the real strategy architecture without forcing redesign

Do **not** automatically default to an extremely small `$500` pilot if that would distort sizing, diversification, minimum-notional behavior, or transaction-cost assumptions. Determine the minimum viable live capital from the final Stable Core sizing rules.

The user does not want to start so small that the architecture immediately requires redesign once live.

## Performance vs Stability Principle

Do not simplify the strategy merely for simplicity.

**Simplify the plumbing, preserve the performance engine.**

Retain strong scanner/strategy components from the better-performing periods where they can be separated from accounting/runtime complexity.

Keep ML and other future enhancement paths alive in the Performance Lab so they can be promoted later without another architectural rewrite.

## Immediate Priority Order for the Next Chat

1. Verify Railway deploys `8fcf06622759cc5775a23361c12de1087f73e4b7` / startup bridge v10.
2. Run only the normal compact daily audit.
3. Inspect the `journal_recovery_candidate` fields from that one audit.
4. Decide whether the append-only journal is a trusted complete recovery source.
5. If yes: design one controlled state rebuild with immutable archive and halt preserved until post-rebuild audit passes.
6. If no: archive contaminated state and intentionally create a **clean accounting epoch** rather than continuing historical repair loops.
7. Begin Stable Core refactor: canonical ledger + account state + execution invariants + single risk controller + single persistence contract.
8. Preserve current rules/scanner performance logic unless evidence shows a specific component is defective.
9. Keep ML/crypto/LONA/MAE-MFE in Performance Lab shadow mode.
10. Start the 5-day Stable Paper v1 clock only after accounting truth is clean.

## Tooling / Connected Services

Use GitHub/Codex tooling for code inspection, implementation, CI, regression review, and deployment work.

LONA is connected and may be used for independent research/backtesting when its frequency interface is usable.

Railway is the canonical deployment environment, but there is no direct Railway connector in the current toolset. Use the user's Railway logs/status and deployed HTTP audit output for live verification.

## Important User Operating Preferences

- Prefer **one routine test link** per day.
- Avoid making the user run multiple diagnostics unless a specific failure requires it.
- Keep the routine audit short enough to copy/paste from iPhone.
- Prefer complete/codebase-level fixes over repeated manual patches.
- Prioritize reaching an operational live-ready system sooner rather than indefinite feature work.
- Do not sacrifice the long-term performance ceiling or future ML capability merely to simplify the current runtime.

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

## Continuation Prompt for New Chat

A new chat should begin by reviewing this file and then checking the latest GitHub `main` head / Railway compact audit.

The most important next question is:

**Does PR #23's append-only journal recovery candidate provide complete, economically consistent execution coverage?**

If yes, perform a controlled recovery. If no, start a clean accounting epoch and move immediately into Stable Core validation rather than continuing to patch contaminated history.
