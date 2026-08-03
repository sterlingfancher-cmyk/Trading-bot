# Automated Trading Project Handoff — Canonical Status, August 3, 2026

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: none; advisory only
- Hard-risk ladder remains unchanged:
  - 1.00% soft realized-loss pause
  - 2.50% hard realized-loss halt
  - 2.50% hard intraday-drawdown halt
  - 3.00% absolute daily-loss ceiling

## Account and Performance Baseline

Latest supplied runtime snapshot at `2026-08-03 11:25:37 CDT`:

- equity: `$10,736.85`
- cash: `$10,240.9964`
- one open paper position: `DELL`
- unrealized P&L: `+$2.05`
- realized today: `$0.00`
- realized lifetime: `+$734.82`
- completed exits: 52
- wins: 35
- losses: 17
- prior lifetime profit factor: approximately `3.18`

The strategy has positive historical paper expectancy. The current engineering objective is reliable participation without loosening the hard-risk ladder.

## Canonical Runtime Architecture

### Scanner stack

Required order:

1. `opening_surge_participation`
2. one `breakout_participation_layer`
3. one `market_participation_accelerator`
4. core scanner

Railway validation at `11:25:02 CDT`:

- `overall: pass`
- one opening-surge wrapper at depth 0
- one breakout wrapper at depth 1
- one market-participation wrapper at depth 2
- `ordered: true`
- `cycle_detected: false`
- `truncated: false`
- no rebuild required

### Public entry stack

Required order:

1. `bear_soft_pause_short_recovery`
2. one Entry Pipeline X-Ray
3. deterministic breakout/composition callable
4. direct core entry pipeline

This stack is composition/ownership only. It must not change signals, thresholds, sizing, hard-risk limits, live authority, ML authority, or place orders directly.

## July 29–31 Repairs

### Performance and regime reliability

- staged performance-risk ladder
- regime-integrity repair
- side-aware bear soft-pause short recovery
- deterministic entry-stack ownership

### Opening-surge participation

July 30 bounded opening-surge valve:

- 15–45 minutes after open
- empty book
- one reduced-size paper position per day
- no confirmed-bear long exception
- strong NQ confirmation
- gap, follow-through, opening-range, near-high, momentum, volume, bucket, and cluster tests

Key versions/commits:

- opening-surge chain-aware v2: `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`
- breakout scanner ownership: `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`
- worker activation: `115e921ecdfeb50fde4b4b1125787e9bb190352d`

July 31 two-stage score calibration:

- raw profiling prefilter `0.012`
- final structurally confirmed score floor `0.045`
- final score cap `0.080`
- structure and cluster tests retained

Commits:

- calibration source: `faf6fab8416c14b5e753b0f909edbebe963bdcac`
- activation: `747a737848de7562035c44507ab81abe694cd11e`

## August 3 Scanner Recursion and Neutral Participation

### Failure evidence

Morning self-check showed an intermittent scanner recursion error at `09:45:34 CDT`:

- `maximum recursion depth exceeded while calling a Python object`
- 25 scanner signals
- zero entries at that snapshot
- market mode `neutral`

A later cycle succeeded, proving the recursion was intermittent. The old self-check also continued to report the prior error as active after later successful cycles.

### Scanner runtime contract

File/version/commit:

- `scanner_runtime_contract.py`
- `scanner-runtime-contract-2026-08-03-v1`
- `77e0ae2d67bcbe1a3e21fe71d86875e8bae67a00`

Behavior:

- bounded callable-chain inspection
- exact scanner layer counts/order
- deterministic rebuild only when missing, duplicated, cyclic, truncated, or misordered
- successful cycles clear stale `last_error` while preserving recovered-error telemetry

Railway validation:

- canonical scanner stack healthy
- no active recursion
- no rebuild required

### Self-check freshness correction

File/version/commit:

- `fast_self_check_override.py`
- `fast-self-check-override-2026-08-03-v4-error-freshness`
- `b6d32ee66aa59e4a9e20b26b8706d597db32a5c6`

Railway validation at `11:08:45 CDT`:

- `overall: pass`
- `last_error: null`
- `last_error_active: false`
- `recursion_error_active: false`
- prior error retained under `last_recovered_error`

## Neutral Momentum Starter

### V1 bounded neutral context

The first neutral extension added a reduced-size starter path from 45–180 minutes after open when:

- market mode exactly `neutral`
- risk score at least 40
- scanner cluster at least 15
- at least four long signals when available
- no confirmed bear or defensive rotation
- no bearish/blocking futures or breadth risk-off confirmation
- positive leadership/tape evidence

The first post-repair cycle opened one paper entry. The current position is `DELL`.

### V2 staged two-position policy

File/version/commit:

- `neutral_momentum_starter_extension.py`
- `neutral-momentum-starter-extension-2026-08-03-v2-staged-two-position`
- `ab10a8ef3fadf956a510f1fcfff4dc22c0201379`

Railway validation at `11:24:26 CDT`:

- `overall: pass`
- `active: true`
- no re-patching on the status call
- maximum entries per day: 2
- maximum entries per cycle: 1
- maximum neutral starter positions: 2
- minimum spacing: 900 seconds
- first-position minimum P&L: `-0.50%`
- maximum combined neutral exposure: `36%`
- second candidate must differ by sector or strategy bucket
- starter allocation factor remains `0.18`
- normal portfolio position cap unchanged
- hard-risk ladder unchanged

A second neutral starter is considered only when:

1. Exactly one first position remains open.
2. At least 15 minutes have elapsed since the latest entry.
3. First-position unrealized P&L is known and at least `-0.50%`.
4. Candidate differs by sector or bucket.
5. Projected combined starter exposure is no more than 36%.
6. Market remains neutral and inside the neutral window.
7. Existing score, rank, quality, cooldown, cash, position, risk, and execution checks independently pass.

Unknown entry time, P&L, or diversification metadata blocks stage two rather than guessing.

## August 3 Entry-Stack Drift Detected

Railway regression output at `11:25:18 CDT` showed:

- `overall: warn`
- `owned: false`
- `entry_guard_active: false` in the final public snapshot
- X-Ray wrapper count `0`
- bear wrapper count varied between `0` and `1` during enforcement
- deterministic composition remained present
- scanner remained healthy
- DELL remained open and account/risk telemetry remained healthy

The prior ownership result showed the public stack was normalized from an X-Ray wrapper, but the rebuild finished without restoring X-Ray. This was a real composition race, not a threshold or strategy problem.

### Root cause

The v1 X-Ray/bear guard intentionally refused to patch when it saw a bear-owned public callable without an immediate X-Ray, expecting the bear stack contract to repair it.

During contract rebuilding:

1. the contract temporarily normalized the public callable to composition;
2. the independent bear watchdog could reinstall the bear wrapper before X-Ray was restored;
3. the v1 X-Ray patcher then saw `bear -> composition` and stood down;
4. the rebuild could finish without X-Ray.

A second ownership issue was also present: the staged neutral valve did not carry the canonical participation-chain version/role. The composition guard could therefore rebuild the base/extended/risk-on helper chain and temporarily remove the staged neutral wrapper until its watchdog reinstalled it.

## August 3 Atomic Entry-Stack Repair

File/version/final source commit:

- `entry_pipeline_xray_bear_ownership_guard.py`
- `entry-pipeline-xray-bear-ownership-2026-08-03-v2-atomic`
- `1786a15e4d0c7fb96adb6e78c057bcde5bac1b62`

Intermediate source commit superseded by the final version:

- `9ae4ee0119f18dbbc9260e8a102273f78c25dfd7`

Behavior:

- serializes contract and direct ownership enforcement with the bear installer lock
- rebuilds the entry stack atomically as:
  - deterministic composition
  - one X-Ray wrapper
  - one bear recovery wrapper
- when X-Ray sees a bear-owned stack missing X-Ray, it performs an atomic repair instead of standing down
- upgrades the already-installed v1 X-Ray ownership guard by exact version comparison
- allows contract enforcement with or without an explicit core argument
- preserves the existing ownership markers expected by the bear stack contract
- patches every neutral extension install so the staged neutral wrapper carries:
  - canonical participation-valve chain version
  - canonical `risk_on_outer` role
  - explicit neutral staged ownership metadata
- prevents the composition guard from removing the staged neutral valve on later integrity passes

Authority boundary:

- paper only
- composition and ownership only
- no signal generation change
- no score or threshold change
- no sizing change
- no hard-risk change
- no direct order placement
- no live or ML authority

No Gunicorn change was required because the existing worker already imports and starts `entry_pipeline_xray_bear_ownership_guard`.

## Post-Deploy Validation

Run in this order after Railway activates commit `1786a15e...` or the later handoff commit:

### 1. Atomic X-Ray/bear ownership

`/paper/entry-pipeline-xray-bear-ownership-status`

Expected:

- version `entry-pipeline-xray-bear-ownership-2026-08-03-v2-atomic`
- `overall: pass`
- `owned: true`
- `valid_xray_below_bear: true`
- `last_install.xray_patch_guard_version` equals the v2 atomic version
- wrapper counts:
  - bear `1`
  - X-Ray `1`
- no duplicate wrapper

The first call may report an atomic repair. Later calls should remain passing without rebuilding.

### 2. Bear stack contract

`/paper/bear-recovery-stack-status`

Expected:

- `overall: pass`
- `owned: true`
- `entry_guard_active: true`
- bear wrapper count `1`
- X-Ray wrapper count `1`
- composition callable remains direct-core based

### 3. Neutral starter ownership

`/paper/neutral-momentum-starter-status`

Expected:

- v2 staged-two-position version
- `overall: pass`
- `active: true`
- `participation_valve_chain_ownership.active: true` when included by the atomic ownership wrapper
- two-per-day, one-per-cycle, 900-second spacing, `-0.50%` first-position floor, 36% combined cap

### 4. Composition status

`/paper/entry-pipeline-composition-status`

Expected:

- `overall: pass`
- `stack_stable: true`
- `recursion_safe: true`
- `participation_valve_chain_cycle_free: true`
- outer participation valve remains the neutral staged wrapper while carrying canonical chain metadata

### 5. Scanner and compact health

- `/paper/scanner-runtime-contract-status`
- `/paper/self-check`

Expected:

- scanner canonical and cycle-free
- compact self-check `overall: pass`
- no active or stale error
- no active recursion
- DELL position preserved unless normally exited by strategy management

### 6. Entry decision visibility

- `/paper/no-entry-diagnostic?force=1`
- `/paper/status`

Use these to confirm:

- current DELL entry price, quantity, entry context, allocation, and unrealized P&L
- whether stage two is outside the neutral window, waiting on spacing/health/diversification, rejected by existing quality controls, or accepted

## Current Definition of Done

Completed and Railway-validated:

- scanner recursion recovery
- canonical scanner ownership
- stale-error telemetry correction
- neutral starter v2 deployment
- first neutral paper entry opened
- DELL position visible with positive unrealized P&L
- no hard-risk or authority regression

Completed in source; Railway validation pending:

- atomic entry-stack ownership v2
- exact one-bear/one-X-Ray restoration
- neutral staged wrapper canonical chain ownership

Do not make another score, threshold, or sizing change until the atomic ownership endpoints pass and the DELL trade/entry context is captured.
