# Automated Trading Project Handoff — Canonical Status, August 3, 2026

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: none; advisory only
- Hard-risk ladder remains:
  - 1.00% realized-loss soft pause
  - 2.50% realized-loss hard halt
  - 2.50% intraday-drawdown hard halt
  - 3.00% absolute daily-equity-loss ceiling

## Account Baseline

Latest supplied account snapshot:

- cash/equity approximately `$10,734.80`
- 52 completed exits before the August 3 cycle
- 35 wins, 17 losses
- realized total `+$734.82`
- lifetime paper profit factor previously approximately `3.18`

The project’s current priority is reliable participation without weakening the proven hard-risk controls.

## Engineering Rules

1. Reliability before performance.
2. Evidence before modification.
3. Do not lower hard-risk controls merely to manufacture activity.
4. Do not add live or ML authority without explicit approval.
5. Avoid recursive main-loop wrappers; use bounded ownership contracts or narrow internal valves.
6. Update this handoff after every material code/configuration change and Railway validation milestone.

## Validated Architecture

### Entry stack

Required order:

1. `bear_soft_pause_short_recovery`
2. one Entry Pipeline X-Ray
3. deterministic composition/breakout callable
4. direct core entry pipeline

Prior Railway validation:

- `owned: true`
- `entry_guard_active: true`
- exactly one bear wrapper
- exactly one X-Ray wrapper
- no entry-stack drift or recursion

### Scanner stack

Required order:

1. `opening_surge_participation`
2. one `breakout_participation_layer`
3. one `market_participation_accelerator`
4. deepest core scanner

Railway validation at `10:57:00 CDT` on August 3:

- `overall: pass`
- opening surge depth `0`
- breakout depth `1`
- market participation depth `2`
- `ordered: true`
- one of each approved layer
- no cycle
- no truncation
- no rebuild required

## Prior Work Summary

### July 29

- staged performance-risk ladder
- regime-integrity repair
- side-aware bear soft-pause short recovery
- deterministic entry-stack ownership

### July 30

Added the bounded opening-surge sleeve:

- 15–45 minutes after open
- empty-book requirement
- strong NQ confirmation
- no confirmed-bear long exception
- gap, follow-through, opening-range, near-high, momentum, volume, bucket, and cluster checks

Key commits:

- opening-surge chain-aware ownership: `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`
- breakout scanner ownership: `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`
- breakout worker activation: `115e921ecdfeb50fde4b4b1125787e9bb190352d`

### July 31

Fixed the raw-score short circuit that prevented candidates from reaching structure analysis:

- raw profiling prefilter `0.012`
- final structure-confirmed floor `0.045`
- final score cap `0.080`
- all existing structure and cluster checks retained

Key commits:

- score calibration: `faf6fab8416c14b5e753b0f909edbebe963bdcac`
- worker activation: `747a737848de7562035c44507ab81abe694cd11e`

Railway Python build repair:

- `mise.toml` commit `4114e77163d921f50aa1d418f4ac709631738046`
- Python remains pinned at 3.11.9
- only unavailable GitHub artifact-attestation verification was disabled

## August 3 Runtime Failure and Recovery

Morning evidence at `10:29:16 CDT` showed:

- scanner found 25 signals
- market mode `neutral`
- no loss, drawdown, halt, self-defense, or open exposure
- `maximum recursion depth exceeded while calling a Python object`

Interpretation:

1. The `09:45` cycle genuinely hit scanner-callable recursion.
2. A later successful cycle proved the failure was intermittent.
3. The old self-check treated the stored error text as still active after recovery.
4. The opening-surge window had ended at `09:15`.
5. The existing starter accepted `risk_on` and `constructive`, but not strong `neutral` tape.

### Scanner runtime contract

File and commit:

- `scanner_runtime_contract.py`
- version `scanner-runtime-contract-2026-08-03-v1`
- commit `77e0ae2d67bcbe1a3e21fe71d86875e8bae67a00`
- route `/paper/scanner-runtime-contract-status`

Behavior:

- bounded callable-graph inspection
- deterministic canonical scanner order
- repair only when missing, duplicated, cyclic, truncated, or misordered
- successful cycles clear stale error telemetry while retaining recovered-error history
- no signal, threshold, sizing, hard-risk, order, live, or ML authority change

### Neutral momentum starter v1

File and commits:

- `neutral_momentum_starter_extension.py`
- v1 `neutral-momentum-starter-extension-2026-08-03-v1`
- source commit `e9f14fdf3221ad9090c048b198d8f745cc4cd34d`
- worker activation `1303d2a3a7ab4c1db874a504c6d7364e810395bc`
- route `/paper/neutral-momentum-starter-status`

Initial bounded context:

- market mode exactly `neutral`
- 45–180 minutes after open
- risk score at least `40`
- scanner cluster at least `15`
- at least four long signals when available
- no confirmed bear or defensive rotation
- no bearish/blocking futures or breadth risk-off confirmation
- positive tape evidence required
- existing candidate score/rank, quality, cooldown, cash, position, risk, and execution controls retained

### First post-repair entry evidence

The cycle completed at `10:58:34 CDT`. The diagnostic at `10:59:46 CDT` reported:

- scanner signals `68`
- long signals `10`
- short signals `2`
- `entries_count: 1`
- verdict `entries_taken_last_cycle`
- market mode `neutral`
- risk score `52`
- longs allowed
- no loss, drawdown, halt, profit guard, or self-defense block

This established that the repaired execution path was no longer structurally stuck flat.

### Self-check freshness repair

File and commit:

- `fast_self_check_override.py`
- version `fast-self-check-override-2026-08-03-v4-error-freshness`
- commit `b6d32ee66aa59e4a9e20b26b8706d597db32a5c6`

Railway validation at `11:08:45 CDT`:

- `overall: pass`
- `last_error: null`
- `last_error_active: false`
- `recursion_error_active: false`
- prior recursion preserved under `last_recovered_error`
- no strategy, threshold, sizing, risk, order, live, or ML authority change

## August 3 Neutral Momentum Starter v2 — Staged Two-Position Policy

File and commit:

- `neutral_momentum_starter_extension.py`
- version `neutral-momentum-starter-extension-2026-08-03-v2-staged-two-position`
- source commit `ab10a8ef3fadf956a510f1fcfff4dc22c0201379`
- existing route remains `/paper/neutral-momentum-starter-status`
- existing Gunicorn import/watchdog remains valid; no startup-file change required

Purpose:

The v1 one-entry limit was appropriate for initial validation but too restrictive as a permanent neutral-market policy. V2 permits a staged second reduced-size starter without changing the normal portfolio position cap.

Base neutral context remains unchanged except that concentrated technology leadership (`tech_concentrated` or `tech_caution`) can count as positive-tape evidence when all other neutral safeguards pass.

### Daily and cycle limits

- maximum neutral starter entries per day: `2`
- maximum starter entries per cycle: `1`
- maximum starter/open-position stage: `2`
- existing starter allocation factor remains `0.18`
- existing raw score floor remains `0.008`
- existing rank score floor remains `0.012`
- normal core candidate quality, ranking, cooldown, execution, and risk controls remain downstream

### Second-entry requirements

A second starter is considered only when all of the following are true:

1. Market mode remains exactly `neutral`.
2. Exactly one first position is still open.
3. At least `900` seconds (15 minutes) have elapsed since the most recent entry.
4. The first position’s unrealized return is known and is not below `-0.50%`.
5. The second candidate differs from the first by sector or strategy bucket.
6. The projected combined neutral-starter exposure does not exceed `36%` of equity.
7. The daily limit of two and cycle limit of one are not exhausted.
8. The existing starter valve independently approves score, rank, preferred leadership, quality-block reason, cash, cooldown, risk state, and execution.

If position time, P&L, or diversification metadata is unavailable, the second starter is blocked rather than guessed.

### Composition safety

V2 patches only `core_entry_pipeline._participation_valve_ok`, not the main entry loop. The wrapper carries the existing risk-on-starter ownership marker so the original starter watchdog does not mistake the staged layer for displacement and create recursive composition.

Authority boundary:

- paper only
- no direct order placement by the extension
- no main-entry-loop wrapper
- no hard-risk change
- no live or ML authority
- no change to the normal portfolio position cap
- no starter sizing increase
- only the neutral starter daily allowance changes from one to two, with stricter second-stage checks

## Post-Deploy Validation

### Neutral starter status

Run:

- `/paper/neutral-momentum-starter-status`

Expected:

- version `neutral-momentum-starter-extension-2026-08-03-v2-staged-two-position`
- `overall: pass`
- `active: true`
- `settings.max_entries_per_day: 2`
- `settings.max_entries_per_cycle: 1`
- `settings.max_open_positions: 2`
- `settings.minimum_seconds_between_entries: 900`
- `settings.first_position_minimum_pnl_pct: -0.5`
- `settings.maximum_combined_exposure_pct: 36.0`
- `settings.requires_different_sector_or_bucket_for_second: true`
- `settings.starter_alloc_factor: 0.18`

The first call after deployment may report that the context and staged valve were patched. Later watchdog/status calls should remain active without adding another layer.

### Regression checks

Run:

- `/paper/scanner-runtime-contract-status`
- `/paper/breakout-scanner-ownership-status`
- `/paper/bear-recovery-stack-status`
- `/paper/self-check`

Expected:

- scanner order still canonical
- one opening-surge, breakout, and market-participation layer
- one bear wrapper and one X-Ray wrapper
- no callable cycle or recursion
- `overall: pass`
- `last_error_active: false`

### Entry diagnostics

Run:

- `/paper/no-entry-diagnostic?force=1`
- `/paper/risk-on-starter-participation-status`
- `/paper/status`

Use `last_evaluation.staged_gate` to identify whether a second entry was:

- waiting for 15-minute spacing
- blocked by first-position loss
- blocked for sector/bucket concentration
- blocked by projected combined exposure
- allowed by the staged gate but rejected by the existing starter/core quality controls
- accepted into the normal paper execution path

## Definition of Done

Completed and Railway-validated:

- scanner recursion diagnosis and canonical recovery
- healthy scanner ordering
- initial bounded neutral starter installation
- one post-repair neutral cycle reached the entry path
- self-check error freshness and recursion recovery telemetry

Completed in source, pending Railway validation:

- two-entry staged neutral starter policy
- 15-minute separation
- second-position diversification
- first-position health gate
- 36% projected combined-exposure cap
- wrapper ownership compatibility with the existing starter watchdog

Do not widen the window, increase starter size, or permit more than two neutral starters until Railway telemetry and actual trade outcomes support another change.

## Exact Next Action

After Railway deploys commit `ab10a8ef3fadf956a510f1fcfff4dc22c0201379`, run in this order:

1. `/paper/neutral-momentum-starter-status`
2. `/paper/scanner-runtime-contract-status`
3. `/paper/bear-recovery-stack-status`
4. `/paper/self-check`
5. `/paper/no-entry-diagnostic?force=1`

Confirm the V2 policy fields, stable ownership, no recursion, and the staged-gate reason before making another strategy or sizing change.
