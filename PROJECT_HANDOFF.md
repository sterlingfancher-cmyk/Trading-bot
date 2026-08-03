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

Latest supplied account snapshot:

- cash/equity approximately `$10,734.80`
- no open positions
- 52 completed exits
- 35 wins, 17 losses
- realized total `+$734.82`
- lifetime profit factor previously measured at approximately `3.18`

The strategy has positive historical paper expectancy. The immediate problem is underdeployment and runtime reliability, not proof that the underlying strategy has negative expectancy.

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
5. The existing risk-on starter accepts only `risk_on` or `constructive`, not `neutral`.
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

This was not a day without opportunity. The runtime and permission architecture failed to convert the available opportunity into a bounded paper entry.

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

The worker now starts and registers both:

- `scanner_runtime_contract`
- `neutral_momentum_starter_extension`

## Post-Deploy Validation

### 1. Scanner runtime contract

`/paper/scanner-runtime-contract-status`

Expected:

- version `scanner-runtime-contract-2026-08-03-v1`
- `overall: pass`
- `after.ordered: true`
- `after.opening_surge_count: 1`
- `after.breakout_count: 1`
- `after.market_participation_count: 1`
- `after.cycle_detected: false`
- `after.truncated: false`
- the first call may report a canonical rebuild; later calls should be stable
- stale recursion telemetry may be moved to recovered-error fields after a confirmed successful cycle

### 2. Neutral momentum starter

`/paper/neutral-momentum-starter-status`

Expected:

- version `neutral-momentum-starter-extension-2026-08-03-v1`
- `overall: pass`
- `active: true`
- window start `45`
- window end `180`
- minimum risk score `40`
- minimum scanner signals `15`
- existing starter allocation factor approximately `0.18`
- existing maximum one starter per day

The endpoint being active means the extension is installed. `last_evaluation` determines whether the current neutral context actually qualifies.

### 3. Runtime regression

Run:

- `/paper/breakout-scanner-ownership-status`
- `/paper/opening-surge-participation-status`
- `/paper/bear-recovery-stack-status`
- `/paper/self-check`

Expected:

- all ownership checks pass
- one opening-surge wrapper
- one breakout wrapper
- one bear wrapper
- one X-Ray wrapper
- no callable cycle or recursion
- a later successful auto cycle should show `last_error: null`

### 4. Entry explanation

Run:

- `/paper/no-entry-diagnostic?force=1`
- `/paper/risk-on-starter-participation-status`

Use these to determine whether a neutral starter was accepted or rejected by score, rank, preferred bucket/symbol, quality, cooldown, risk, or execution controls.

## Definition of Done

Completed in source:

- Aug. 3 recursion and stale-error diagnosis
- canonical scanner runtime contract
- stale recursion telemetry recovery
- bounded neutral momentum starter
- worker startup and route registration
- handoff update

Pending Railway validation:

- scanner runtime contract passes and remains stable after a watchdog interval
- later successful cycle clears stale recursion warning
- neutral starter endpoint passes
- ownership and compact self-check remain healthy
- during an eligible neutral momentum window, one qualified candidate reaches the normal core entry pipeline
- any resulting position remains one reduced-size paper starter
- collect entry and outcome evidence before widening the window, increasing size, or adding more daily entries

## Exact Next Action

After Railway deploys commit `1303d2a3a7ab4c1db874a504c6d7364e810395bc`, run:

1. `/paper/scanner-runtime-contract-status`
2. `/paper/neutral-momentum-starter-status`
3. `/paper/self-check`
4. `/paper/no-entry-diagnostic?force=1`

Do not make another threshold or sizing change until these four responses show whether the runtime recovered and whether the bounded neutral starter reached the existing quality/execution path.