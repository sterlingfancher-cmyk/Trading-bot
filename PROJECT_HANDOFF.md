# Automated Trading Project Handoff — Canonical Status, August 3, 2026

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: advisory only
- Hard-risk ladder unchanged:
  - 1.00% soft realized-loss pause
  - 2.50% hard realized-loss halt
  - 2.50% hard intraday-drawdown halt
  - 3.00% absolute daily-loss ceiling

## Latest Account Snapshot

Railway snapshot at `2026-08-03 12:12:53 CDT`:

- equity: `$10,738.02`
- cash: `$10,240.9964`
- open paper position: `DELL`
- unrealized P&L: `+$3.22`
- realized today: `$0.00`
- realized lifetime: `+$734.82`
- completed exits: 52
- wins/losses: 35/17
- prior lifetime profit factor: approximately `3.18`

## Canonical Scanner Stack

Required order:

1. `opening_surge_participation`
2. one `breakout_participation_layer`
3. one `market_participation_accelerator`
4. core scanner

Current Railway validation:

- component `scanner_stack`: pass
- opening-surge count 1
- breakout count 1
- market-participation count 1
- `ordered: true`
- `cycle_detected: false`
- `truncated: false`
- no rebuild required

Source:

- `scanner_runtime_contract.py`
- version `scanner-runtime-contract-2026-08-03-v1`
- commit `77e0ae2d67bcbe1a3e21fe71d86875e8bae67a00`

## Canonical Public Entry Stack

Required order:

1. `bear_soft_pause_short_recovery`
2. one Entry Pipeline X-Ray
3. deterministic breakout/composition callable
4. direct core entry pipeline

Atomic ownership source:

- `entry_pipeline_xray_bear_ownership_guard.py`
- version `entry-pipeline-xray-bear-ownership-2026-08-03-v2-atomic`
- commit `1786a15e4d0c7fb96adb6e78c057bcde5bac1b62`

Current Railway validation:

- component `entry_stack_ownership`: pass
- `owned: true`
- `valid_xray_below_bear: true`
- `entry_guard_active: true`
- bear wrapper count 1
- X-Ray wrapper count 1
- atomic repair reason `already_owned`

Composition validation:

- component `entry_composition`: pass
- `stack_stable: true`
- `recursion_safe: true`
- `direct_core_base: true`
- participation chain cycle-free
- active participation valve is `neutral_momentum_starter_extension.staged_valve`

Bear contract validation:

- component `bear_recovery_stack`: pass
- `owned: true`
- `entry_guard_active: true`
- bear wrapper count 1
- X-Ray wrapper count 1

The ownership/composition modules do not change signals, thresholds, sizing, hard-risk limits, live authority, ML authority, or place orders directly.

## Recursion and Error Freshness

Earlier August 3 failure:

- scanner recursion at `09:45:34 CDT`
- `maximum recursion depth exceeded while calling a Python object`

Current status:

- successful cycles superseded the failure
- latest successful cycle: `12:07:39 CDT`
- `last_error: null`
- no active or historical recursion flag in the current self-check
- prior failure retained under recovered-error telemetry

## Neutral Momentum Starter

### Staged policy

- maximum entries per day: 2
- maximum entries per cycle: 1
- maximum staged starter positions: 2
- minimum spacing: 900 seconds
- first-position minimum unrealized return: `-0.50%`
- maximum combined exposure: `36%`
- second candidate must differ by sector or strategy bucket
- allocation factor remains `0.18`
- normal portfolio cap and hard-risk ladder unchanged

### Neutral-only staging v3

Source:

- `neutral_momentum_starter_extension.py`
- version `neutral-momentum-starter-extension-2026-08-03-v3-neutral-only-staging`
- commit `9be472986c6624139833d48bf4e52201f7416205`

Behavior:

- neutral staging checks apply only when market mode is exactly `neutral`
- `constructive`, `risk_on`, and other non-neutral contexts pass through to the original starter
- old neutral wrappers are replaced rather than stacked
- downstream score, rank, quality, cooldown, cash, risk, position, and execution checks remain unchanged

Railway validation at `12:12:53 CDT`:

- component `neutral_starter`: pass
- `active: true`
- `neutral_only_staging: true`
- maximum entries per day 2
- maximum entries per cycle 1
- maximum open positions 2
- minimum spacing 900 seconds
- combined exposure cap 36%
- last gate reason `non_neutral_passthrough`
- last gate status `non_neutral_passthrough_allowed`

This confirms the v2 defect is repaired: a constructive/risk-on candidate is no longer rejected merely because the neutral stage requires neutral mode.

## Single Routine Test

Source:

- `fast_self_check_override.py`
- version `fast-self-check-override-2026-08-03-v5-all-in-one`
- commit `b95d8548fb6bfc2b03fa90b9657f1e08da4127d4`

Routine link:

`https://trading-bot-clean.up.railway.app/paper/self-check`

The endpoint validates:

1. scanner stack
2. atomic entry-stack ownership
3. entry composition and recursion safety
4. bear-recovery stack
5. neutral starter
6. account, auto-runner, risk, error freshness, signals, and positions

Railway validation at `12:12:53 CDT`:

- type `all_in_one_self_check`
- version `fast-self-check-override-2026-08-03-v5-all-in-one`
- `one_test_complete: true`
- top-level `overall: pass`
- components checked 5
- components passed 5
- components warned 0
- `failing_components: []`
- `base_failures: []`
- `next_action: none`
- no active error
- no halt
- no self-defense activation
- auto-runner enabled and thread started

## Validation Workflow Going Forward

Routine operation requires only:

`/paper/self-check`

When `overall: pass`, no other endpoint is required.

Open an individual endpoint only when its component name appears in `summary.failing_components`. Use `/paper/full-self-check` only for intentional troubleshooting.

## Definition of Done

Completed and Railway-validated:

- scanner recursion recovery
- canonical scanner ownership
- stale-error telemetry correction
- first neutral paper entry
- DELL position opened and managed normally
- staged two-position neutral policy
- neutral-only v3 passthrough
- atomic public entry-stack ownership
- exactly one bear and one X-Ray wrapper
- all-in-one self-check v5
- one-link routine validation workflow

Next evidence requirement:

- observe DELL management/exit and several staged-neutral outcomes before any further score, sizing, risk, or window expansion
