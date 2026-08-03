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

## Latest Account Baseline

Supplied all-in-one snapshot at `2026-08-03 12:12:53 CDT`:

- equity: `$10,738.02`
- cash: `$10,240.9964`
- one open paper position: `DELL`
- unrealized P&L: `+$3.22`
- realized today: `$0.00`
- realized lifetime: `+$734.82`
- completed exits: 52
- wins/losses: 35/17
- scanner signals: 41
- market/risk snapshot: neutral, no loss, no drawdown, no halt, no self-defense

The account remained materially underdeployed with only one small position despite healthy risk and scanner state.

## Canonical Scanner Stack

Required order:

1. `opening_surge_participation`
2. one `breakout_participation_layer`
3. one `market_participation_accelerator`
4. core scanner

Validated:

- one of each approved scanner layer
- correct order
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

Validated:

- `owned: true`
- one bear wrapper
- one X-Ray wrapper
- valid X-Ray below bear
- direct-core composition
- no drift or recursion

## Neutral Starter Core Policy

Source:

- `neutral_momentum_starter_extension.py`
- version `neutral-momentum-starter-extension-2026-08-03-v3-neutral-only-staging`
- commit `9be472986c6624139833d48bf4e52201f7416205`

Validated settings:

- maximum starter entries per day: 2
- maximum entries per cycle: 1
- maximum staged starter positions: 2
- minimum spacing: 900 seconds
- first-position minimum P&L in the base window: `-0.50%`
- maximum combined exposure: 36%
- second candidate must differ by sector or strategy bucket
- allocation factor remains `0.18`
- normal portfolio cap remains 6
- constructive/risk-on candidates pass through unchanged

## Underdeployment Finding at 12:15 CDT

The one-link test showed every runtime component passing, but only DELL was open.

This was not caused by:

- portfolio capacity
- risk halt
- self-defense
- scanner failure
- entry-stack drift
- recursion
- active loss or drawdown

The remaining mechanical constraint was the neutral starter context window. It ended 180 minutes after the regular open, or `11:30 CDT`. By approximately `12:15 CDT`, the account still had one small position and 41 scanner signals, but the neutral exception could no longer admit a second starter.

## Bounded Late Neutral Participation

Source:

- `neutral_late_session_participation.py`
- version `neutral-late-session-participation-2026-08-03-v1`
- source commit `cff93fc2631a45b793cd4ed2aa372166ffbe9e81`
- worker activation commit `f23a511fa48955951ce7d01eb59d1820eb1c6db2`

Behavior:

- extends the neutral context window from 180 to 300 minutes after open
- new final neutral cutoff: `13:30 CDT`
- retains two entries per day, one per cycle, two staged starter positions, 18% allocation factor, and 36% combined exposure cap
- does not change the normal portfolio cap

The late segment from 180–300 minutes requires:

- market mode exactly neutral
- risk score at least 50
- at least 30 scanner signals
- candidate score at least `0.025`
- no risk halt or self-defense
- no realized daily loss
- intraday drawdown no greater than 0.50%
- for a second starter, the first position must be non-losing at `0.00%` or better
- existing spacing, diversification, quality, cooldown, cash, execution, and risk checks still pass

Current supplied evidence would satisfy the broad context inputs:

- risk score previously 52
- scanner signals 41
- DELL unrealized P&L positive
- no loss, drawdown, halt, or self-defense

A second position is still not forced. A candidate must independently clear the candidate-score and all original downstream controls.

Authority boundary:

- paper only
- no direct order placement
- no hard-risk change
- no starter-sizing change
- no normal portfolio-cap change
- no live or ML authority

## Single Routine Test

Source:

- `fast_self_check_override.py`
- version `fast-self-check-override-2026-08-03-v5-all-in-one`
- commit `b95d8548fb6bfc2b03fa90b9657f1e08da4127d4`

Routine link:

`https://trading-bot-clean.up.railway.app/paper/self-check`

The late-session module adds a sixth component to this same response:

- `neutral_late_window`

Expected after Railway deploys the activation commit:

- top-level type `all_in_one_self_check`
- top-level `overall: pass`
- `components_checked: 6`
- `components_passed: 6`
- `components_warned: 0`
- `failing_components: []`
- `base_failures: []`
- `neutral_late_window.overall: pass`
- `neutral_late_window.active: true`
- `extended_window_end_minutes: 300`
- `late_minimum_risk_score: 50`
- `late_minimum_scanner_signals: 30`
- `late_minimum_candidate_score: 0.025`
- `late_minimum_first_position_pnl_pct: 0.0`

Run no other endpoint unless its component name appears under `summary.failing_components`.

## Definition of Done

Completed and Railway-validated:

- scanner recursion recovery
- canonical scanner ownership
- stale-error telemetry correction
- first neutral paper entry
- neutral-only constructive/risk-on passthrough
- staged two-position neutral policy
- atomic entry-stack ownership
- one bear and one X-Ray wrapper
- all-in-one self-check v5

Completed in source; Railway validation pending:

- bounded late neutral participation v1
- six-component all-in-one self-check result

Next evidence requirement:

- confirm the one-link test passes with six components
- observe whether the late neutral window admits a second independent position
- do not expand score, sizing, exposure, or hard-risk limits until several late-neutral outcomes are recorded
