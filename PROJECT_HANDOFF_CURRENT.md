# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-21 14:36 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Current `main`: `da691224875aebf1464903be6f90937ee6dfaf01` (PR #105)  
Active PR: #106 `agent/sls-bad-execution-recovery-proof-20260821`  
Authoritative paper runtime for Issue #82 validation: `https://web-production-e1796.up.railway.app`  
Contaminated split-lineage service: `https://trading-bot-clean.up.railway.app`

## Communication / Continuity Rule

Keep Trading-bot progress communication in the currently active ChatGPT project conversation. When intentionally moving chats, refresh this file first, stop at a clean boundary, and treat the new conversation as active. Project-specific monitoring tasks remain disabled unless explicitly re-established. Warn before the current conversation becomes too large for reliable continuation.

## Safety / Authority Boundaries

- Paper-only until explicit approval.
- Rules remain sole execution authority; ML/AI remains shadow-only.
- Never manually clear a halt, rewrite `day_peak_equity`, force a fresh-day baseline, restore an older state backup, or overwrite state from an incomplete reconstruction.
- Never delete, edit, fabricate, or relabel canonical execution-ledger rows.
- Never change strategy, normal signal thresholds, sizing, hard-risk thresholds, live authority, or ML authority merely to make an audit pass.
- Do not casually call `/paper/run`; use read-only diagnostics unless an explicit validation plan requires a cycle.
- Every relevant change must pass the exact-head Change Safety Audit plus focused regressions, repository validation, architecture/ownership/config/debt checks, and exact Gunicorn bootstrap smoke before merge.
- While Issue #82 remains open, authoritative runtime changes must map to a demonstrated safety defect or #94 governance/validation requirement.

## Executive Status

Issue #82 remains the stabilization exit gate.

The central discovery on Aug. 21 is that the two Railway services are **different persistent-state lineages running the same code**. The `trading-bot-clean` volume is contaminated legacy state and is not the Aug. 12 verified successor. The historically canonical `web-production-e1796` service still carries the mechanically proven `stable-paper-v2-20260812-verified01` lineage.

Do not design recovery from the `trading-bot-clean` volume. Use `web-production-e1796` for all current #82 economic/risk validation until a deliberate service/volume consolidation is separately designed and proven.

The authoritative v2 account is structurally/accounting coherent except for two known immutable bad executions:
1. the historical duplicate TEM full exit, prospectively blocked by PR #81; and
2. a newly proven Aug. 21 SLS partial-profit execution at `186.2901` against an entry near `14.335`, prospectively blocked by PR #105.

The account remains hard-halted because persisted `day_peak_equity=19150.437724108448` is not supported by retained equity observations. Do not clear the halt or rewrite the peak yet.

## Split Railway State Lineage — Decisive Aug. 21 Evidence

### `trading-bot-clean` contaminated lineage

Read-only provenance on the clean-domain service showed:
- account cash/equity about `-26064.31`
- zero positions
- 303 state trade rows
- stale risk day 2026-08-20 with `day_peak_equity=0.01`
- canonical ledger 55 rows, all epoch `legacy-pre-stable-core`
- retained backups and eight retained snapshots contain no Aug. 12 verified epoch object/signature
- trade journal and backup contain no verified v2 top-level marker

This volume is healthy persistence of the wrong historical lineage. No current backup should be restored.

### `web-production-e1796` verified successor lineage

`/paper/canonical-execution-ledger-status` proved:
- `current_epoch_id=stable-paper-v2-20260812-verified01`
- hash chain valid
- no parse/hash errors
- 36 rows when first checked; later compact audit reported 37 rows
- authoritative execution hook active

`/paper/fresh-day-check` proved sane current-day initialization:
- date `2026-08-21`
- `day_start_equity=13166.470921819817`
- `day_peak_equity=19150.437724108448`
- `fresh_day_reset_pending=false`
- baseline status `pass`

Therefore the correct v2 lineage survived on the older Railway service and the earlier negative-account investigation was occurring on a separate persistent-state boundary.

## Authoritative v2 Runtime Evidence — Aug. 21

### Self-check

At about 13:13 CDT:
- cash `13159.073498029464`
- equity about `13542.62`
- positions `DHR`, `GH`, `SLS`, `TOST`
- realized today `+368.68`
- unrealized about `+6.46`
- runner enabled, recent successful automatic cycles, no active runner error
- all nine bounded runtime component checks passed
- risk remained halted only because persisted intraday drawdown was about `29.283%`

### Compact daily audit

At 13:37 CDT:
- account cash `13159.073498029464`
- equity `13541.79`
- verified epoch `stable-paper-v2-20260812-verified01`
- baseline type `verified_snapshot_with_open_position`
- historical recovery decision `verified_snapshot_rollforward`
- starting cash `10768.497730982748`
- starting equity `11885.824057382748`
- historical evidence archived `true`
- validation hold remains active / release blocked
- reconstructed cash `13159.07351`
- reconstructed equity `13541.791832`
- reconstructed positions exactly `DHR`, `GH`, `SLS`, `TOST`
- market data pass with 3527/3527 classified terminal outcomes and no in-flight requests
- runner pass / no active error
- canonical ledger chain valid, active v2, 37 rows

The only accounting warning is the already-known immutable duplicate TEM full exit:
- entry `29.640567 @ 54.885`, execution `d647d8a0580b44edbab0224e6c339bfd`
- first full exit `29.640567 @ 53.105`, execution `7b13d9194a23407f926667b2f48d4057`
- duplicate full exit `29.640567 @ 52.905`, execution `3530dbf965db4894ba93b7098cec3696`

PR #81 prospectively prevents recurrence. Never delete/rewrite/relabel the historical TEM row.

## Day-Peak Forensics

PR #104 merged as `9c724d4feb268c5705634c65790314e4912ece45` and added read-only `/paper/day-peak-provenance-status`.

Authoritative v2 result:
- current equity about `13541.73`
- day start `13166.470921819817`
- persisted day peak `19150.437724108448`
- current change from day start about `+2.85%`
- reported drawdown from persisted peak about `29.288%`
- rolling equity history max only `14285.11`
- retained history does **not** contain the current risk peak
- no current-day compiled report headline contains the current risk peak
- diagnosis `current_risk_peak_not_proven_by_retained_equity_observations`

Important retained history boundary:
- history around max moved from roughly `13166` to `14285.11` and immediately back near `13537`
- this proved at least one transient valuation spike but did not explain the full `19150.44` risk peak

Do not rewrite the peak from this probe alone. The $19,150 peak still requires independent provenance/correction proof.

## Newly Proven SLS Bad Execution — Aug. 21

Current-day state evidence:
- SLS entry execution `4dfe9d5b3e50432c820723ea9a39dcb0`
- entry `6.497145 @ 14.335`
- bogus partial-profit execution `b6584fe0e28744d8bfa2da26f413af70`
- partial exit `2.144058 @ 186.2901`
- exit reason `partial_profit_long`
- current remaining shares about `4.353086829`
- current SLS `peak=186.2901`

Independent Alpaca IEX evidence gathered after the incident:
- exact quote window around 14:50:30–14:51:35 UTC had bids roughly `14.16–14.23` and asks `14.26–14.27`
- nearby IEX 1-minute bars were roughly `14.105–14.29`
- no SLS forward/reverse split corporate action was reported for Aug. 18–22
- recorded bad price `186.2901` was about `13.05x` the contemporaneous IEX ask and about `13.0x` the position entry

Economic consequence of the exact bad partial exit:
- bogus cash proceeds `2.144058 * 186.2901 = 399.4167792258`
- bogus realized PnL `(186.2901 - 14.335) * 2.144058 = 368.6817077958`
- this explains essentially the entire audit `realized_today=368.68`
- before the partial exit, marking all SLS shares near 186 also explains the retained equity-history spike to about `14285`

The SLS event proves the accounting system can be internally coherent while faithfully reconstructing an economically invalid execution. The immutable bad execution must remain preserved as forensic evidence; recovery must use a successor-state/accounting disposition, not ledger editing.

## PR #105 — Symmetric Favorable Quote Integrity

PR #105 merged as `da691224875aebf1464903be6f90937ee6dfaf01` after final exact-head Change Safety Audit, focused quote-integrity regressions, repository safety, architecture/ownership/config/debt checks, and exact Gunicorn startup smoke all passed. Both Railway deployment contexts subsequently reported success.

Runtime confirmation on `web-production-e1796`:
- version `paper-exit-price-integrity-2026-08-21-v3-symmetric-position-anchor`
- `long_min_price_ratio=0.4`
- `long_max_price_ratio=2.5`
- `short_min_price_ratio=0.4`
- `short_max_price_ratio=2.5`
- `position_entry_anchor_enabled=true`
- valuation fallback installed
- `symmetric_favorable_outlier_protection=true`
- overall `pass`

Prospective behavior now blocks catastrophic favorable **and** adverse marks at fresh/cache, valuation-fallback, full-exit, and partial-exit boundaries. It does not change normal stops, strategy, sizing, live/ML authority, historical state, ledger rows, day peak, or halt state.

## PR #106 — Read-only SLS Bad-Execution Recovery Proof

Active branch: `agent/sls-bad-execution-recovery-proof-20260821`.

Purpose: prove mechanically whether the exact invalid SLS partial exit is terminal in the canonical ledger and whether a deterministic arithmetic counterfactual can be formed without editing history.

Planned route: `/paper/sls-bad-execution-recovery-proof`.

The route is reporting/counterfactual only. On explicit access it:
- verifies exact SLS entry and bad partial-exit signatures in state trades;
- line-reads the canonical ledger through its existing read/verify helpers and confirms hash-chain health;
- reports whether any canonical executions occur after the bad SLS row;
- checks current remaining SLS shares plus the bad-exit quantity reconcile to the original entry quantity;
- records the independent IEX evidence described above;
- computes the exact reversal arithmetic using the already-stored current SLS mark for valuation only;
- does not fabricate a replacement fill price;
- does not write state, edit/relabel/delete ledger rows, rewrite SLS peak/day peak, clear the halt, place orders, or change strategy/risk/sizing/live/ML authority.

If the bad SLS execution is the final canonical execution and all signatures reconcile, the route may classify the counterfactual as mechanically proven. That still does **not** authorize a state mutation; the candidate must next be compared against independent account/valuation evidence and then wrapped in a separate exact-signature successor migration under validation hold.

If later canonical executions exist, they must be replayed deterministically after removing only the bad event's economic effect before any migration can be considered.

## Durable Verified-Recovery Provenance

GitHub history independently proves the Aug. 12 successor existed:
- PR #45 `9b659c88f77d5004e82ee0dda8e6d26c074621e8`: exact LRCX bad-tick recovery and creation of `stable-paper-v2-20260812-verified01`
- PR #46 `16c4c2371e46d23d15057f172a37756ff5245342`: journal-lock deadlock fix after the recovery
- PR #48 `b5ea9d9192f7ac7cf65d8e342d11727ac3249b2b`: explicit successful v1→v2 successor compatibility
- PR #52 `d82f6eb327c90dede362fc0160167ac8c18c327f`: canonical ledger already authoritative for v2 and compact reporting fixed to use active successor epoch

Verified baseline constants from the recovery remain:
- starting cash `10768.497730982748`
- starting equity `11885.824057382748`
- restored LRCX `3.42486 @ 312.90`, verified mark `326.24`

The clean-domain volume lost these runtime markers, but the `web-production` volume currently proves the v2 lineage directly through its active state and canonical ledger.

## Startup-Liveness Observation

After several Aug. 21 deployments, `/bootstrap-status` repeatedly spent >60 seconds in `runtime_worker_registration` while:
- loader thread remained alive
- 5-second registration heartbeat continued advancing
- pre-WSGI fresh-day guard remained installed/pass
- application eventually became ready

This is currently a slow cold-start condition, not a proven hang. If registration remains in the same broad phase for roughly 4–5 minutes or heartbeat stops advancing, treat it as a separate Issue #82 startup-liveness defect and add per-subphase timing/progress telemetry before changing registration behavior.

Current `runtime_worker_registration.py` is an older synchronous stack with no per-component timing telemetry. Do not guess the slow component and do not parallelize/refactor registration without evidence.

## Issue #82 — Stabilization Exit Gate

Already satisfied/prospectively contained:
- #56 source terminal-price plausibility
- #79 fresh cached quote provenance/plausibility
- #80 catastrophic persisted `last_price` fallback block
- #81 duplicate full-exit preflight guard
- #83/#87 fresh-day baseline sanity and pre-WSGI installation
- #98 removal of X-Ray stale-file authoritative overwrite
- canonical v2 service lineage mechanically rediscovered
- sane fresh-day initialization on the v2 service
- #105 symmetric favorable/adverse quote-integrity containment

Still required:
1. mechanically prove the exact SLS successor-account counterfactual and any later-execution replay requirement;
2. separately prove the source/correction boundary for the unsupported `$19,150.44` day peak;
3. preserve immutable TEM and SLS bad executions while establishing an evidence-based successor accounting disposition;
4. perform any recovery only through an exact-signature, archived, validation-hold migration — never manual state edits;
5. obtain one normal forward paper market session with runner/accounting/ledger/market-data/quote-integrity/execution healthy and no new accounting category;
6. obtain clean active audit with sane valuation, valid canonical chain, no active economic/coverage issue except explicitly archived predecessor evidence, and risk reflecting actual economics.

Authoritative canary/cutover/performance expansion remains blocked until #82 is satisfied.

## Stable Paper Core v3 / Issue #84

Merged shadow/parity stages:
- #85 Stage A immutable canonical models / ownership contract
- #89 Stage B deterministic valuation snapshot
- #90 Stage C canonical risk engine shadow parity
- #91 Stage D StateStore transaction boundary
- #92 Stage E ledger-derived accounting projection
- #93 Stage F bounded paper-canary planner, shadow only

Stage G/cutover remains blocked by #82 and parity. Do not use shadow core to bypass stabilization.

## Mandatory Change Safety / Issue #94

PR #95 established the exact-head Change Safety Audit. Every relevant PR must pass:
- impact-aware focused regressions + Stable Paper Core invariants
- repository validation
- structural architecture audit
- ownership validation
- typed configuration parity
- architecture-debt regression gate
- exact Gunicorn bootstrap smoke
- final exact-head decision

Later extensions:
- #101/#102/#103 provenance regressions
- #104 day-peak provenance regression
- #105 focused price-integrity regressions
- #106 adds focused SLS recovery-proof regression

Repository branch protection on `main` was still not enabled when last checked; in-repository gate remains mandatory regardless.

## Self-Diagnosing Sentinel / Issue #96

PR #97 remains advisory/shadow only. It may classify incidents and recommend tests/remediation but may not write state, repair accounting, clear halts, edit execution history, change strategy/sizing/hard risk/live/ML authority, or auto-merge authoritative repairs.

## Architecture Program

Aug. 20 master audit baseline: about 250 Python files / 90,409 LOC, 34 runtime mutation overlaps, 5 env conflicts, 5 route overlaps, 80 duplicate-function groups, 540 broad exception-pass sites, 8 watchdog loops, 32 critical findings. Fragmented owners included `save_state` 17, `scan_signals` 14, `try_entries_and_rotations` 13, `entry_quality_check` 10, `enter_position` 9.

Canonical owners remain:
- signals → `trading.signals.SignalEngine`
- decisions → `trading.decision.DecisionEngine`
- state → `trading.state.StateStore`
- entry quality → `trading.decision.EntryQualityPolicy`
- execution → `trading.execution.PaperExecutionService`
- exits → `trading.execution.ExitManager`
- market data → `trading.market_data.MarketDataAdapter`
- cycle runtime → `trading.runtime.CycleOrchestrator`
- rotations → `trading.decision.RotationPolicy`
- market regime → `trading.market.MarketRegimeService`

No big-bang rewrite. Cut over one authority boundary at a time after parity/proof and delete the legacy owner only afterward.

## Known CI / Ops Debt

A separate `daily-operational-audit` workflow remains red from stale expectations that predate the latest provenance/quote work:
1. next-action precedence expectation for an old recursion fixture;
2. curated audit fixture expects `pass` instead of current `warn`;
3. bootstrap overlay test expects obsolete `v6-registration-heartbeat` while production is now v7.

Do not change runtime accounting/risk behavior merely to satisfy these stale expectations. Fix them separately under Issue #94 when not interleaving with the active SLS/risk forensics sequence.

## Current Runtime Links

For Issue #82 authoritative validation use the verified v2 service:
- bootstrap: `https://web-production-e1796.up.railway.app/bootstrap-status`
- fresh-day: `https://web-production-e1796.up.railway.app/paper/fresh-day-check`
- self-check: `https://web-production-e1796.up.railway.app/paper/self-check`
- compact daily audit: `https://web-production-e1796.up.railway.app/paper/daily-audit`
- full daily audit: `https://web-production-e1796.up.railway.app/paper/daily-audit?full=1`
- canonical ledger: `https://web-production-e1796.up.railway.app/paper/canonical-execution-ledger-status`
- day-peak provenance: `https://web-production-e1796.up.railway.app/paper/day-peak-provenance-status`
- quote-integrity status: `https://web-production-e1796.up.railway.app/paper/exit-price-integrity-status`
- SLS recovery proof after PR #106 deploy: `https://web-production-e1796.up.railway.app/paper/sls-bad-execution-recovery-proof`

Do not use `trading-bot-clean` as authoritative economic evidence until the split-volume consolidation is separately designed and proven.

## Exact Next Action

Finish PR #106 under the mandatory exact-head safety gate. After deployment, call only the authoritative v2 `/paper/sls-bad-execution-recovery-proof` route. If it proves the bad SLS row is terminal and the exact reversal reconciles, compare that counterfactual against independent account/valuation evidence before designing any exact-signature successor migration. Do not clear the halt or rewrite the `$19,150.44` risk peak during this sequence.
