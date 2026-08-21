# Project Handoff — Authoritative Current Runtime

Last updated: 2026-08-21 16:45 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Current `main`: `b7f685e460ec31fa1f93987ff29704c01bed650a` (PR #109)  
Active PR: consolidated verified-v2 recovery gate on `agent/consolidated-v2-recovery-gate-20260821`  
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

The central Aug. 21 discovery is that the two Railway services are **different persistent-state lineages running the same code**. `trading-bot-clean` is contaminated legacy state and is not the Aug. 12 verified successor. The historically canonical `web-production-e1796` service still carries the mechanically proven `stable-paper-v2-20260812-verified01` lineage.

Do not design recovery from `trading-bot-clean`. Use `web-production-e1796` for all #82 economic/risk validation until a deliberate service/volume consolidation is separately designed and proven.

The authoritative v2 canonical ledger is hash-chain valid, currently 39 rows, all in `stable-paper-v2-20260812-verified01`. Five immutable executions now have independent evidence that their economic effects are invalid and must be excluded only from a counterfactual successor projection while their rows remain untouched:

1. TEM duplicate full exit `3530dbf965db4894ba93b7098cec3696`, exact immutable price `52.904999`, qty `29.640567`.
2. SLS catastrophic favorable partial exit `b6584fe0e28744d8bfa2da26f413af70`, exact immutable price `186.2901`, qty `2.144057692`.
3. TOST catastrophic favorable partial exit `fd685aa6387247ff99a05e7386c325e9`, `1.24333584 @ 73.940002`.
4. TOST catastrophic favorable partial exit `cb10928f441148aaa3faf041a84bc4c8`, `1.24333584 @ 190.244995`.
5. TOST catastrophic favorable partial exit `1451d91c06b34b199364b56f72ad376f`, `1.24333584 @ 74.269997`.

The account remains hard-halted because persisted `day_peak_equity=19150.437724108448` is unsupported by retained equity observations. Do not clear the halt or rewrite the peak. The preferred recovery path is to correct successor economic state under validation hold while leaving the current-day halt/peak untouched, then allow the next legitimate fresh-risk-day initialization to occur prospectively from sane corrected economics.

## Split Railway State Lineage — Decisive Aug. 21 Evidence

### `trading-bot-clean` contaminated lineage

Read-only provenance showed:
- cash/equity about `-26064.31`
- zero positions
- 303 state trade rows
- stale risk day 2026-08-20 with `day_peak_equity=0.01`
- canonical ledger 55 rows, all `legacy-pre-stable-core`
- retained backups/snapshots do not preserve the Aug. 12 verified v2 epoch
- trade journal/backup have no verified v2 top-level marker

This service is healthy persistence of the wrong historical state boundary. Do not restore its backups or use it as authoritative account evidence.

### `web-production-e1796` verified successor lineage

Direct runtime evidence proved:
- `current_epoch_id=stable-paper-v2-20260812-verified01`
- canonical hash chain valid with no parse/hash errors
- authoritative execution hook active
- sane current-day baseline initialization
- runner/market-data healthy on settled self-check/audit

The service initially showed 36 canonical rows, then 37, then 39 as additional executions were appended. All remain in the verified v2 epoch.

## Authoritative v2 Account / Audit Evidence — Aug. 21

Settled self-check around 13:13 CDT:
- cash `13159.073498029464`
- equity about `13542.62`
- positions `DHR`, `GH`, `SLS`, `TOST`
- realized today `+368.68`
- runner enabled / no active error
- all bounded runtime component checks passed
- risk halted solely because persisted intraday drawdown was about 29.28%

Compact daily audit around 13:37 CDT:
- account cash `13159.073498029464`
- equity `13541.79`
- verified epoch `stable-paper-v2-20260812-verified01`
- baseline type `verified_snapshot_with_open_position`
- historical recovery decision `verified_snapshot_rollforward`
- starting cash `10768.497730982748`
- starting equity `11885.824057382748`
- validation hold remains active / release blocked
- reconstructed cash `13159.07351`
- reconstructed equity `13541.791832`
- reconstructed positions exactly `DHR`, `GH`, `SLS`, `TOST`
- market-data accounting complete and provider circuit clear
- runner pass / no active error
- ledger chain valid

The audit's original single coverage warning was the historical TEM duplicate. Subsequent forensics proved the account/ledger could still be internally coherent while carrying economically impossible quote-derived fills.

## Day-Peak Forensics — PR #104

PR #104 merged as `9c724d4feb268c5705634c65790314e4912ece45` and added read-only `/paper/day-peak-provenance-status`.

Authoritative result:
- current equity about `13541.73`
- day start `13166.470921819817`
- persisted day peak `19150.437724108448`
- current change from day start about `+2.85%`
- reported drawdown from persisted peak about `29.288%`
- rolling equity history maximum only `14285.11`
- retained history does **not** contain the current risk peak
- no current-day compiled report headline contains the current risk peak
- diagnosis `current_risk_peak_not_proven_by_retained_equity_observations`

The retained history did capture a transient jump from roughly `13166` to `14285.11` and immediately back near `13537`, proving at least one transient valuation spike. The later SLS evidence explains that retained jump, but not the entire unsupported `19150.44` risk peak.

## SLS Bad Execution — PRs #105 / #106

SLS entry:
- execution `4dfe9d5b3e50432c820723ea9a39dcb0`
- canonical entry quantity about `6.497144521 @ 14.335`

Bad partial exit:
- execution `b6584fe0e28744d8bfa2da26f413af70`
- exact canonical qty `2.144057692 @ 186.2901`
- exit reason `partial_profit_long`

Independent Alpaca IEX evidence at the execution window:
- bids roughly `14.16–14.23`
- asks roughly `14.26–14.27`
- nearby 1-minute range about `14.105–14.29`
- no SLS split/reverse-split action Aug. 18–22

The bogus row created about `$399.42` cash proceeds and about `$368.68` realized PnL, explaining essentially all reported `realized_today`. It also left SLS `peak=186.2901` and explains the retained equity-history spike near `14285`.

PR #105 merged as `da691224875aebf1464903be6f90937ee6dfaf01`. It prospectively added symmetric favorable/adverse quote-integrity protection using the broad 0.40x..2.50x position-entry anchor at fresh/cache, valuation fallback, full-exit, and partial-exit boundaries. Runtime confirmed version `paper-exit-price-integrity-2026-08-21-v3-symmetric-position-anchor`, `position_entry_anchor_enabled=true`, `symmetric_favorable_outlier_protection=true`, overall pass.

PR #106 merged as `8a42729fcf89dad5ab7de8df39073c727b8873a9`. Its read-only SLS recovery proof established that the SLS bad row was not terminal: three canonical TOST partial exits followed it.

## Successor Replay / TOST Evidence — PR #107

PR #107 merged as `28d5a2a318b83fbdc0dce361571836e699734a19` and added deterministic read-only verified-v2 successor replay.

Runtime result:
- ledger chain valid
- row count 39
- all rows verified-v2
- SLS signature exact
- TEM row found once but initial expected display price `52.905` missed the immutable canonical value by one micro-dollar
- three canonical rows after SLS were all TOST partial-profit exits
- `state.trades` contained zero rows after SLS, showing those TOST rows were not reflected in current state economics

Independent Alpaca IEX checks on the three TOST rows:
- 13:11:11 CDT: recorded `73.940002`, market roughly `36.21–36.25`
- 14:03:17 CDT: recorded `190.244995`, market roughly `36.44–36.47`
- 14:35:20 CDT: recorded `74.269997`, market roughly `36.39–36.44`
- no TOST forward/reverse/unit split action Aug. 18–22

All three TOST rows are catastrophic favorable outliers. Their immutable rows must remain preserved, but their economic effects must not be replayed into a corrected successor state.

## TEM Precision Provenance — PR #109

PR #109 merged as `b7f685e460ec31fa1f93987ff29704c01bed650a` after exact-head Change Safety, Architecture Debt, Repository Safety, full Refactor/Ownership/Config/Startup audit, and Gunicorn smoke passed. Both Railway deployments succeeded.

Runtime TEM provenance:
- execution ID, epoch, action, symbol, side, quantity all exact
- only failed field was price
- observed immutable canonical price `52.904999`
- prior expected display value `52.905`
- absolute difference about `0.000001`

This is serialization/display precision provenance, not a new economic contradiction. The successor gate must use the immutable canonical value `52.904999` and should not broadly loosen price tolerance.

## Consolidated Recovery-Gate Policy — Current Work

Too many one-off manual tests accumulated during Aug. 21 forensics. The current work consolidates them into the existing single route:

`/paper/verified-v2-successor-replay-status`

The consolidated gate:
- exact-matches all five known invalid immutable rows at canonical precision;
- verifies ledger chain, epoch, unique execution IDs, and terminal ordering;
- excludes only those five rows from counterfactual economics while retaining every row in the immutable ledger;
- replays every other canonical execution in original order from the exact Aug. 12 verified baseline;
- compares projected positions/cash/equity against current state and flags unexplained differences outside known-invalid symbols;
- reports current risk state but does not change it;
- sets `manual_per_event_probe_required=false` when mechanically complete;
- never writes state, rewrites the day peak, clears the halt, fabricates a fill, edits history, places orders, or changes strategy/risk/sizing/live/ML authority.

The one-off SLS recovery-proof and TEM field-provenance modules remain in repository history/tests for evidence but are removed from startup route registration once the consolidated gate lands. The day-peak provenance route remains registered because the unsupported risk peak is still a separate #82 evidence boundary.

After the consolidated gate deploys, the assistant should query it directly. Do not ask the user to run another per-event forensic endpoint. If the consolidated gate passes, proceed to design the bounded exact-signature successor-state migration under validation hold.

## Durable Verified-Recovery Provenance

GitHub history independently proves the Aug. 12 successor existed:
- PR #45 `9b659c88f77d5004e82ee0dda8e6d26c074621e8`: exact LRCX bad-tick recovery and creation of `stable-paper-v2-20260812-verified01`
- PR #46 `16c4c2371e46d23d15057f172a37756ff5245342`: journal-lock deadlock fix after recovery
- PR #48 `b5ea9d9192f7ac7cf65d8e342d11727ac3249b2b`: explicit successful v1→v2 successor compatibility
- PR #52 `d82f6eb327c90dede362fc0160167ac8c18c327f`: canonical ledger already authoritative for v2 and reporting fixed to use active successor epoch

Verified baseline constants:
- starting cash `10768.497730982748`
- starting equity `11885.824057382748`
- restored LRCX `3.42486 @ 312.90`, verified mark `326.24`

## Startup-Liveness Observation

Several Aug. 21 deployments spent >60 seconds in `runtime_worker_registration` while the loader thread and heartbeat remained alive and the pre-WSGI fresh-day guard remained pass. The app eventually became ready. Treat this as slow cold start, not a proven hang, unless the same broad phase persists roughly 4–5 minutes or heartbeat stops.

Do not guess or parallelize registration. If it becomes a real blocker, first add per-component read-only timing/progress telemetry. Consolidating superseded forensic registrations is allowed when directly replacing them with one owned route; do not use startup latency as justification for broad runtime refactors.

## Issue #82 — Stabilization Exit Gate

Already satisfied/prospectively contained:
- #56 terminal-price plausibility
- #79 cached quote freshness/provenance
- #80 catastrophic persisted `last_price` fallback block
- #81 duplicate full-exit preflight guard
- #83/#87 fresh-day baseline sanity + pre-WSGI installation
- #98 X-Ray stale-state overwrite repair
- authoritative v2 service lineage rediscovered
- sane fresh-day initialization on authoritative v2 service
- #105 symmetric favorable/adverse quote-integrity containment
- exact immutable provenance for TEM, SLS, and three TOST bad executions

Still required:
1. get the consolidated five-execution verified-v2 recovery gate mechanically complete;
2. perform any economic recovery only through an exact-signature, archived, validation-hold successor migration; never manual edits;
3. leave the current-day halt/peak untouched unless a separate exact evidence boundary explicitly authorizes correction;
4. obtain a sane next fresh-risk-day initialization from corrected economics;
5. obtain one normal forward paper market session with runner/accounting/ledger/market-data/quote-integrity/execution healthy and no new accounting category;
6. obtain a clean active audit with sane valuation, valid canonical chain, no active economic/coverage issue except archived predecessor evidence, and risk reflecting actual economics;
7. only after #82, deliberately consolidate Railway service/domain/state boundary and continue Stable Paper Core v3 cutover.

## Stable Paper Core v3 / Issue #84

Merged shadow/parity stages:
- #85 Stage A immutable canonical models / ownership contract
- #89 Stage B deterministic valuation snapshot
- #90 Stage C canonical risk engine shadow parity
- #91 Stage D StateStore transaction boundary
- #92 Stage E ledger-derived accounting projection
- #93 Stage F bounded paper-canary planner, shadow only

Stage G/cutover remains blocked by #82. Do not use shadow core to bypass stabilization.

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

Later focused extensions cover provenance, day-peak, price-integrity, SLS recovery proof, and verified-v2 successor replay. Repository branch protection on `main` was still not enabled when last checked; the in-repo gate remains mandatory regardless.

## Self-Diagnosing Sentinel / Issue #96

PR #97 remains advisory/shadow only. It may classify incidents and recommend tests/remediation but may not write state, repair accounting, clear halts, edit execution history, change strategy/sizing/hard risk/live/ML authority, or auto-merge authoritative repairs.

## Architecture Program

Aug. 20 master audit baseline: about 250 Python files / 90,409 LOC, 34 runtime mutation overlaps, 5 env conflicts, 5 route overlaps, 80 duplicate-function groups, 540 broad exception-pass sites, 8 watchdog loops, 32 critical findings.

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

A separate `daily-operational-audit` workflow remains red from stale expectations that predate current runtime behavior:
1. old next-action/recursion fixture ordering;
2. curated audit fixture expecting `pass` instead of current `warn`;
3. bootstrap overlay expecting obsolete `v6-registration-heartbeat` while production is v7.

Treat this as #94 governance debt. Do not change runtime accounting/risk/strategy to satisfy stale fixtures.

## Current Runtime Links

Authoritative v2 service:
- bootstrap: `https://web-production-e1796.up.railway.app/bootstrap-status`
- self-check: `https://web-production-e1796.up.railway.app/paper/self-check`
- compact daily audit: `https://web-production-e1796.up.railway.app/paper/daily-audit`
- canonical ledger: `https://web-production-e1796.up.railway.app/paper/canonical-execution-ledger-status`
- quote-integrity: `https://web-production-e1796.up.railway.app/paper/exit-price-integrity-status`
- day-peak provenance: `https://web-production-e1796.up.railway.app/paper/day-peak-provenance-status`
- single consolidated recovery gate after current deploy: `https://web-production-e1796.up.railway.app/paper/verified-v2-successor-replay-status`

Do not use `trading-bot-clean` as authoritative economic evidence until split-volume consolidation is separately designed and proven.

## Exact Next Action

Finish the consolidated recovery-gate PR under the mandatory exact-head safety gate. After authoritative Railway deployment succeeds, the assistant should query `/paper/verified-v2-successor-replay-status` directly rather than asking the user to run another one-off test. If diagnosis is `verified_v2_consolidated_recovery_gate_mechanically_complete`, use that single result as the sole forensic runtime input for a bounded successor-state migration design under validation hold. Do not clear the current halt or rewrite `day_peak_equity` during that sequence.
