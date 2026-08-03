# Automated Trading Project Handoff — Canonical Status, August 3, 2026

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: none; advisory only
- No repair in this handoff changes the 1.00% soft-pause, 2.50% hard realized-loss halt, 2.50% hard intraday-drawdown halt, or 3.00% absolute daily-loss ceiling.

## Account Baseline

Latest supplied account snapshot before the August 3 entry cycle:

- cash/equity approximately `$10,734.80`
- no open positions before `10:58:34 CDT`
- 52 completed exits
- 35 wins, 17 losses
- realized total `+$734.82`
- lifetime profit factor previously measured at approximately `3.18`

The strategy has positive historical paper expectancy. The immediate problem was underdeployment and runtime reliability, not proof that the underlying strategy had negative expectancy.

## Engineering Rules

1. Reliability before performance.
2. Evidence before modification.
3. Do not lower hard-risk controls to manufacture activity.
4. Do not add live or ML authority without explicit approval.
5. Avoid recursive callable wrappers; prefer deterministic ownership contracts or bounded internal extensions.
6. Every material code/configuration change and Railway validation milestone must update this handoff.

## Validated Architecture Before August 3

### Entry stack

Required order:

1. `bear_soft_pause_short_recovery`
2. one Entry Pipeline X-Ray
3. deterministic composition/breakout callable
4. direct core entry pipeline

Prior Railway validation showed:

- `owned: true`
- `entry_guard_active: true`
- exactly one bear wrapper
- exactly one X-Ray wrapper
- no drift or recursion in the entry stack

### Scanner stack

Required order:

1. `opening_surge_participation`
2. exactly one `breakout_participation_layer`
3. `market_participation_accelerator`
4. deepest core scanner

Prior Railway validation showed one opening-surge wrapper, one breakout wrapper, opening surge above breakout, and no callable cycle.

## Prior Reliability and Participation Work

### July 29

- staged performance-risk ladder
- regime-integrity repair
- side-aware bear soft-pause short recovery
- deterministic entry-stack ownership

Key routes:

- `/paper/performance-risk-activation-status`
- `/paper/regime-integrity-status`
- `/paper/bear-short-recovery-status`
- `/paper/bear-recovery-stack-status`
- `/paper/entry-pipeline-xray-bear-ownership-status`

### July 30

A missed bullish opening in a defensive historical regime led to a bounded opening-surge valve:

- 15–45 minutes after open
- empty book
- one reduced-size paper position per day
- no confirmed-bear long exception
- strong NQ opening confirmation
- gap/follow-through/opening-range/near-high/momentum/volume/bucket/cluster tests

Key commits:

- opening-surge v2 chain-aware ownership: `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`
- breakout scanner ownership source: `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`
- breakout scanner worker activation: `115e921ecdfeb50fde4b4b1125787e9bb190352d`

### July 31

The first real opening test showed the fixed raw score floor `0.045` prevented candidates from reaching structure analysis. A two-stage calibration was added:

- raw profiling prefilter `0.012`
- final structurally confirmed score floor `0.045`
- final score cap `0.080`
- all existing structure and cluster tests retained

Key commits:

- score calibration source: `faf6fab8416c14b5e753b0f909edbebe963bdcac`
- worker activation: `747a737848de7562035c44507ab81abe694cd11e`

Build recovery:

- `mise.toml` commit `4114e77163d921f50aa1d418f4ac709631738046`
- Python remains pinned at 3.11.9
- only GitHub artifact-attestation verification was disabled for the unavailable prebuilt attestation

## August 3 Failure Evidence

Fast self-check generated at `2026-08-03 10:29:16 CDT` showed:

- auto-runner enabled at 300-second cadence
- `last_attempt: 09:45:34 CDT`
- `last_error: maximum recursion depth exceeded while calling a Python object`
- `last_success: 09:54:39 CDT`
- `recursion_error_active: true`
- scanner found 25 signals
- zero entries
- market mode `neutral`
- no loss, drawdown, halt, self-defense, or open exposure

Interpretation:

1. The `09:45` cycle genuinely hit scanner-callable recursion and could not reliably complete the entry path.
2. A later cycle succeeded at `09:54`, proving the recursion was intermittent rather than a permanent worker crash.
3. The compact self-check treated the old error string as still active because successful cycles did not clear `last_error`.
4. The bounded opening-surge valve had already closed at `09:15`.
5. The existing risk-on starter accepted only `risk_on` or `constructive`, not `neutral`.
6. Therefore a strong neutral tape after `09:15` had no bounded starter path even when many valid momentum names existed.

User-supplied charts around `10:30 CDT` showed broad strength and orderly intraday advances in:

- RGIT approximately `+7.19%`
- APLD approximately `+7.03%`
- MP approximately `+5.29%`
- NBIS approximately `+11.97%`
- AMZN approximately `+5.23%`
- META approximately `+6.65%`
- BTQ approximately `+5.48%`
- NVTS approximately `+5.02%`
- KEEL approximately `+4.16%`
- CIFR approximately `+8.42%`

This was not a day without opportunity. The runtime and permission architecture failed to convert the available opportunity into a bounded paper entry before the repair.

## August 3 Repair 1 — Scanner Runtime Contract

New file:

- `scanner_runtime_contract.py`
- version `scanner-runtime-contract-2026-08-03-v1`
- commit `77e0ae2d67bcbe1a3e21fe71d86875e8bae67a00`
- route `/paper/scanner-runtime-contract-status`

Behavior:

- inspects the callable graph with bounded cycle detection
- requires exactly one opening-surge wrapper, one breakout wrapper, and one market-participation wrapper
- requires the order `opening surge -> breakout -> market participation -> core`
- if the chain is missing, duplicated, cyclic, truncated, or misordered, restores the known core scanner and reapplies only the approved layers
- preserves the opening-surge score calibration after a rebuild
- patches `set_auto_success` so a successful cycle clears stale `last_error` and `last_error_trace`
- preserves the prior error in `last_recovered_error` fields for auditability
- runs a recurring watchdog

Authority boundary:

- composition and reliability only
- no signal criteria change
- no score/threshold change
- no sizing change
- no hard-risk change
- no direct orders
- no live or ML authority

## August 3 Repair 2 — Bounded Neutral Momentum Starter

New file:

- `neutral_momentum_starter_extension.py`
- version `neutral-momentum-starter-extension-2026-08-03-v1`
- commit `e9f14fdf3221ad9090c048b198d8f745cc4cd34d`
- route `/paper/neutral-momentum-starter-status`

This does not wrap the main entry loop. It extends only the existing risk-on starter's market-context test.

Neutral context may qualify only when:

- paper context
- regular session open
- market mode exactly `neutral`
- 45–180 minutes after open (`09:15–11:30 CDT`)
- risk score at least `40`
- no bear confirmation
- no defensive rotation
- no bearish/blocking futures context
- no breadth risk-off confirmation
- scanner cluster at least 15 signals
- at least four long signals when a long count is available
- positive tape evidence from growth leadership, multiple risk-on sectors, supportive/bullish futures, or supportive/narrow leadership breadth

The existing starter still controls final tradability:

- one starter per day and one per cycle
- existing allocation factor `0.18`
- existing raw-score and rank-score floors
- preferred leadership bucket/symbol requirement
- quality-block allowlist and hard-block tokens
- clean risk state
- cash and open-position limits
- cooldowns and normal core execution controls

Additional universe hints/mappings:

- RGIT, APLD, MP, NBIS, AMZN, META, BTQ, NVTS, KEEL, CIFR

Authority boundary:

- paper only
- no direct order placement by the extension
- no main-entry-loop wrapper
- no hard-risk, live-authority, ML-authority, position-limit, or starter-sizing change
- only a bounded neutral market-context permission is added

## Worker Activation

`gunicorn.conf.py` activation commit:

- `1303d2a3a7ab4c1db874a504c6d7364e810395bc`

The worker starts and registers both:

- `scanner_runtime_contract`
- `neutral_momentum_starter_extension`

## Railway Validation — August 3, 10:57–10:59 CDT

### Scanner runtime contract

At `10:57:00 CDT`:

- version `scanner-runtime-contract-2026-08-03-v1`
- `overall: pass`
- canonical stack already healthy; no rebuild required
- one opening-surge layer at depth `0`
- one breakout layer at depth `1`
- one market-participation layer at depth `2`
- `ordered: true`
- `cycle_detected: false`
- `truncated: false`
- no threshold, sizing, signal, risk, live, or ML authority change

This validates the scanner runtime repair in Railway.

### Neutral momentum starter installation

At `10:57:22 CDT`:

- version `neutral-momentum-starter-extension-2026-08-03-v1`
- `overall: pass`
- `active: true`
- no re-patching on the status call
- window `45–180` minutes after open
- minimum risk score `40`
- minimum scanner cluster `15`
- existing starter allocation factor `0.18`
- existing one-entry-per-day limit preserved
- existing raw score floor `0.008`
- existing rank score floor `0.012`

`last_evaluation` was empty because the status call occurred before the first scanner/entry cycle after installation.

### First post-repair entry cycle

The cycle completed at `10:58:34 CDT` and the no-entry diagnostic generated at `10:59:46 CDT` reported:

- scanner found `68` signals
- `10` long signals and `2` short signals
- `entries_count: 1`
- `exits_count: 0`
- verdict `entries_taken_last_cycle`
- primary driver `entries_taken`
- market mode `neutral`
- risk score `52`
- longs allowed
- new entries allowed
- no loss, drawdown, halt, profit guard, or self-defense block
- the account was no longer stuck flat

The earlier `10:57:41` self-check showing zero positions was generated before this `10:58:34` cycle and was therefore one cycle stale. Do not use that snapshot to conclude the repair failed.

The exact selected symbol was not present in the supplied diagnostic. Confirm it from `/paper/status`, `/paper/self-check`, or the starter telemetry before attributing the entry to a particular ticker.

### Remaining stale-error telemetry defect

The `10:57:41` self-check still displayed the old `09:45` recursion message as active even though successful cycles had occurred at `10:50:14` and `10:58:34`. The scanner contract itself reported no recursion error and a healthy callable chain. Therefore this was a freshness-reporting defect, not an active scanner failure.

Repair:

- file `fast_self_check_override.py`
- version `fast-self-check-override-2026-08-03-v4-error-freshness`
- commit `b6d32ee66aa59e4a9e20b26b8706d597db32a5c6`

Behavior:

- compares the last error attempt with later run/success timestamps
- labels a superseded error `historical_superseded`
- reports `last_error_active: false` and `last_error_stale: true` when a later successful cycle exists
- keeps the historical error text for auditability
- reports recursion as historical rather than active
- changes telemetry only; no strategy, threshold, sizing, risk, order, live, or ML authority

## Validation Endpoints

Runtime and ownership:

- `/paper/scanner-runtime-contract-status`
- `/paper/breakout-scanner-ownership-status`
- `/paper/opening-surge-participation-status`
- `/paper/bear-recovery-stack-status`
- `/paper/entry-pipeline-xray-bear-ownership-status`

Entry and account state:

- `/paper/status`
- `/paper/self-check`
- `/paper/no-entry-diagnostic?force=1`
- `/paper/risk-on-starter-participation-status`
- `/paper/neutral-momentum-starter-status`

## Definition of Done

Completed and Railway-validated:

- Aug. 3 recursion diagnosis
- canonical scanner runtime contract
- exact scanner ordering with one of each approved layer
- bounded neutral momentum starter installation
- first post-repair neutral cycle reached the entry path
- one paper entry opened at `10:58:34 CDT`
- no hard-risk or authority regression

Completed in source, pending redeploy validation:

- fast self-check error-freshness correction
- historical recursion warning should no longer make `/paper/self-check` warn after a later successful cycle

Still required:

- identify the selected symbol and entry context from current account/starter telemetry
- confirm the position uses the intended reduced-size starter allocation
- observe management and exit behavior
- collect outcome evidence before widening the neutral window, increasing size, or allowing more daily entries

## Exact Next Action

After Railway deploys commit `b6d32ee66aa59e4a9e20b26b8706d597db32a5c6`, run:

1. `/paper/self-check`
2. `/paper/status`
3. `/paper/risk-on-starter-participation-status`
4. `/paper/neutral-momentum-starter-status`

Expected self-check telemetry:

- version `fast-self-check-override-2026-08-03-v4-error-freshness`
- `overall: pass`
- `last_error_active: false`
- old recursion message either absent or marked `last_error_stale: true`
- `recursion_error_active: false`
- `recursion_error_historical: true` if the old text remains

Use the account and starter outputs to identify the opened symbol, entry context, allocation, entry price, and current unrealized P&L. Do not make another threshold or sizing change until that evidence is captured.