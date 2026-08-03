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

## Current Account Baseline

Latest supplied snapshot at `2026-08-03 11:42:36 CDT`:

- equity: `$10,736.85`
- cash: `$10,240.9964`
- open paper position: `DELL`
- unrealized P&L: `+$2.05`
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

Railway validation:

- `overall: pass`
- one opening-surge wrapper
- one breakout wrapper
- one market-participation wrapper
- `ordered: true`
- no cycle or truncation
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

Railway validation at `11:41:09–11:41:41 CDT`:

- `overall: pass`
- `owned: true`
- `valid_xray_below_bear: true`
- `entry_guard_active: true`
- bear wrapper count 1
- X-Ray wrapper count 1
- no drift or repair required
- composition remains direct-core based and recursion-safe

This repair changes composition/ownership only. It does not change signals, thresholds, sizing, hard-risk limits, live authority, ML authority, or place orders directly.

## Recursion and Error Freshness

Earlier August 3 failure:

- scanner recursion at `09:45:34 CDT`
- `maximum recursion depth exceeded while calling a Python object`

Current status:

- later successful cycles superseded the failure
- `last_error: null`
- no active recursion
- historical failure retained only as recovered-error telemetry

## Neutral Momentum Starter

### Staged two-position policy

Existing limits retained:

- maximum entries per day: 2
- maximum entries per cycle: 1
- maximum staged starter positions: 2
- minimum spacing: 900 seconds
- first-position minimum unrealized return: `-0.50%`
- maximum combined exposure: `36%`
- second candidate must differ by sector or strategy bucket
- allocation factor: `0.18`
- normal portfolio cap and hard-risk ladder unchanged

### Neutral-only staging v3

Source:

- `neutral_momentum_starter_extension.py`
- version `neutral-momentum-starter-extension-2026-08-03-v3-neutral-only-staging`
- commit `9be472986c6624139833d48bf4e52201f7416205`

Reason for v3:

- v2 incorrectly returned `second_starter_requires_neutral_mode` for WDC and NBIS while their supplied market context was `constructive`
- this blocked the original constructive/risk-on starter before it could evaluate those candidates

V3 behavior:

- neutral staging checks apply only when market mode is exactly `neutral`
- `constructive`, `risk_on`, and other non-neutral contexts pass through to the original starter
- old neutral wrappers are replaced instead of stacked
- normal score, rank, quality, cooldown, cash, risk, position, and execution checks remain downstream
- no hard-risk, live-authority, ML-authority, main-entry-loop, or direct-order change

Railway validation of v3 remains pending.

## Single Routine Test

### All-in-one self-check

Source:

- `fast_self_check_override.py`
- version `fast-self-check-override-2026-08-03-v5-all-in-one`
- commit `b95d8548fb6bfc2b03fa90b9657f1e08da4127d4`

Routine test link:

- `/paper/self-check`

The single endpoint now runs and summarizes:

1. scanner-stack ownership/order
2. atomic entry-stack ownership
3. entry-pipeline composition and recursion safety
4. bear-recovery stack ownership
5. neutral starter installation and staged settings
6. account, auto-runner, risk, error freshness, scanner counts, and open positions

The response remains compact. Each component returns only its key version, pass/warn state, ownership/count fields, and current gate reason.

Top-level summary fields:

- `components_checked`
- `components_passed`
- `components_warned`
- `failing_components`
- `base_failures`
- `next_action`

Top-level `overall: pass` requires:

- no active auto-runner error
- no risk halt
- no self-defense activation
- auto-runner/thread not explicitly disabled
- every component check passing

The endpoint may perform the same bounded composition/ownership repair that the individual ownership endpoints already perform. It does not change trading strategy, thresholds, sizing, risk limits, live authority, or ML authority.

## New Validation Workflow

After Railway deploys the latest commits, run only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Expected:

- type `all_in_one_self_check`
- version `fast-self-check-override-2026-08-03-v5-all-in-one`
- `one_test_complete: true`
- `components_checked: 5`
- `components_warned: 0`
- `failing_components: []`
- `base_failures: []`
- top-level `overall: pass`

Expected component results:

- `scanner_stack.overall: pass`
- `entry_stack_ownership.overall: pass`
- `entry_composition.overall: pass`
- `bear_recovery_stack.overall: pass`
- `neutral_starter.overall: pass`

Expected neutral component after v3 deployment:

- version `neutral-momentum-starter-extension-2026-08-03-v3-neutral-only-staging`
- `neutral_only_staging: true`
- maximum entries per day 2
- maximum entries per cycle 1
- maximum open positions 2
- minimum spacing 900 seconds
- combined exposure cap 36%

Use an individual endpoint only when its component name appears in `failing_components`. Full diagnostics remain available at `/paper/full-self-check` for intentional troubleshooting, not routine testing.

## Definition of Done

Completed and Railway-validated:

- scanner recursion recovery
- canonical scanner ownership
- stale-error telemetry correction
- first neutral paper entry
- DELL opened and managed normally
- staged two-position neutral policy v2 installation
- atomic public entry-stack ownership
- exactly one bear and one X-Ray wrapper

Completed in source; Railway validation pending:

- neutral starter v3 non-neutral passthrough
- all-in-one self-check v5

Do not make another score, size, risk, or window change until the one-link self-check passes and several staged-neutral outcomes are observed.
