# Automated Trading Project Handoff — Canonical Status, August 3, 2026

## Operating Boundary

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway: `https://trading-bot-clean.up.railway.app`
- Mode: paper only
- Live broker authority: none
- ML execution authority: none; advisory only
- Hard-risk ladder unchanged:
  - 1.00% soft realized-loss pause
  - 2.50% hard realized-loss halt
  - 2.50% hard intraday-drawdown halt
  - 3.00% absolute daily-loss ceiling

## Current Account State

Latest supplied account snapshot at `2026-08-03 11:42:36 CDT`:

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

## Canonical Scanner Stack

Required order:

1. `opening_surge_participation`
2. one `breakout_participation_layer`
3. one `market_participation_accelerator`
4. core scanner

Railway validation at `11:25:02 CDT`:

- `overall: pass`
- opening-surge count 1 at depth 0
- breakout count 1 at depth 1
- market-participation count 1 at depth 2
- `ordered: true`
- `cycle_detected: false`
- `truncated: false`
- no rebuild required

Scanner reliability source:

- `scanner_runtime_contract.py`
- version `scanner-runtime-contract-2026-08-03-v1`
- commit `77e0ae2d67bcbe1a3e21fe71d86875e8bae67a00`

## Canonical Public Entry Stack

Required order:

1. `bear_soft_pause_short_recovery`
2. one Entry Pipeline X-Ray
3. deterministic breakout/composition callable
4. direct core entry pipeline

### Atomic ownership repair

Source:

- `entry_pipeline_xray_bear_ownership_guard.py`
- version `entry-pipeline-xray-bear-ownership-2026-08-03-v2-atomic`
- final source commit `1786a15e4d0c7fb96adb6e78c057bcde5bac1b62`

Railway validation at `11:41:09–11:41:41 CDT`:

- `overall: pass`
- `owned: true`
- `valid_xray_below_bear: true`
- `entry_guard_active: true`
- bear wrapper count 1
- X-Ray wrapper count 1
- known wrapper depth 3
- no drift
- no repair required on the status call
- deterministic composition remains direct-core based
- neutral staged valve preserved in the canonical participation chain

The atomic repair closes the prior watchdog race by serializing stack reconstruction with the bear installer lock.

Authority boundary:

- composition and ownership only
- no signal-generation change
- no threshold change
- no sizing change
- no hard-risk change
- no direct orders
- no live or ML authority

## Self-Check and Recursion State

Earlier August 3 failure:

- scanner recursion at `09:45:34 CDT`
- error: `maximum recursion depth exceeded while calling a Python object`

Repairs:

- canonical scanner runtime contract
- successful-cycle error clearing
- self-check freshness logic

Self-check source:

- `fast_self_check_override.py`
- version `fast-self-check-override-2026-08-03-v4-error-freshness`
- commit `b6d32ee66aa59e4a9e20b26b8706d597db32a5c6`

Latest supplied self-check at `11:42:36 CDT`:

- `overall: pass`
- `last_error: null`
- `last_error_active: false`
- `recursion_error_active: false`
- prior recursion retained only under recovered-error telemetry

## Opening-Surge Participation

Opening-surge ownership:

- chain-aware v2 commit `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`

Breakout ownership:

- source commit `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`
- worker activation `115e921ecdfeb50fde4b4b1125787e9bb190352d`

Two-stage opening score calibration:

- raw profiling prefilter `0.012`
- final structure score floor `0.045`
- final cap `0.080`
- source commit `faf6fab8416c14b5e753b0f909edbebe963bdcac`
- activation commit `747a737848de7562035c44507ab81abe694cd11e`

## Neutral Momentum Starter

### V2 staged two-position policy

Source commit:

- `ab10a8ef3fadf956a510f1fcfff4dc22c0201379`

Validated settings:

- maximum entries per day: 2
- maximum entries per cycle: 1
- maximum starter/open-position stage: 2
- minimum spacing: 900 seconds
- first-position minimum unrealized return: `-0.50%`
- maximum combined exposure: `36%`
- second candidate must differ by sector or strategy bucket
- starter allocation factor remains `0.18`
- normal portfolio cap unchanged
- hard-risk ladder unchanged

### Railway evidence that exposed the v2 mode leak

At `11:41:01` and `11:42:12 CDT`, the staged gate evaluated WDC and NBIS while the supplied market mode was `constructive`.

The v2 wrapper returned:

- `second_starter_requires_neutral_mode`

This happened before the original constructive/risk-on starter could evaluate the candidates. The neutral stage constraints should apply only in neutral mode; stronger non-neutral modes must pass through to the pre-existing starter.

The compact self-check at `11:42:36 CDT` separately reported a neutral risk snapshot. These are different telemetry moments and do not invalidate the earlier constructive evaluations.

### V3 neutral-only staging repair

Source:

- `neutral_momentum_starter_extension.py`
- version `neutral-momentum-starter-extension-2026-08-03-v3-neutral-only-staging`
- commit `9be472986c6624139833d48bf4e52201f7416205`

Behavior:

- replaces any older neutral staged wrapper instead of stacking above it
- replaces any older neutral context wrapper
- applies spacing, first-position health, diversification, and exposure checks only when market mode is exactly `neutral`
- for `constructive`, `risk_on`, and other non-neutral modes, calls the pre-existing starter directly
- records `non_neutral_passthrough` telemetry
- preserves the two-per-day, one-per-cycle neutral policy and existing `0.18` allocation factor
- keeps all normal score, rank, quality, cooldown, cash, risk, position, and execution checks downstream
- does not change the main entry loop, hard-risk limits, live authority, or ML authority

No Gunicorn update is required because the existing worker already imports and watches `neutral_momentum_starter_extension`.

## Current Railway Validation Status

Completed and passing:

- scanner canonical and cycle-free
- atomic entry stack ownership
- exactly one bear wrapper
- exactly one X-Ray wrapper
- deterministic composition direct-core based
- neutral staged valve present in canonical participation chain
- compact self-check passing
- no active recursion
- DELL position preserved with positive unrealized P&L

Pending deployment validation:

- neutral starter v3
- non-neutral passthrough must no longer return `second_starter_requires_neutral_mode`

## Post-Deploy Validation

Run:

1. `/paper/neutral-momentum-starter-status`
2. `/paper/entry-pipeline-xray-bear-ownership-status`
3. `/paper/entry-pipeline-composition-status`
4. `/paper/bear-recovery-stack-status`
5. `/paper/self-check`

Expected neutral starter status:

- version `neutral-momentum-starter-extension-2026-08-03-v3-neutral-only-staging`
- `overall: pass`
- `active: true`
- `settings.non_neutral_passthrough_unchanged: true`
- `authority.neutral_stage_applies_only_in_neutral_mode: true`
- max entries per day 2
- max entries per cycle 1
- 900-second spacing
- first-position floor `-0.50%`
- combined exposure cap `36%`

Expected entry-stack regression:

- atomic ownership version remains v2
- `owned: true`
- bear wrapper count 1
- X-Ray wrapper count 1
- composition `stack_stable: true`
- participation chain cycle-free
- no recursion

After a scanner cycle:

- in neutral mode, `last_evaluation.staged_gate` may report spacing, health, diversification, exposure, prior quality rejection, or stage-two allowance
- in constructive/risk-on mode, `last_evaluation.staged_gate.reason` should be `non_neutral_passthrough`, with the original starter result preserved
- it must not report `second_starter_requires_neutral_mode` for a non-neutral market

## Definition of Done

Completed:

- scanner recursion repair
- stale-error telemetry repair
- first neutral paper entry
- DELL position opened and managed normally
- staged two-position neutral policy
- atomic entry-stack ownership repair
- exact one-bear/one-X-Ray Railway validation

Pending:

- Railway validation of neutral starter v3 non-neutral passthrough
- continued observation of DELL management and exit
- collection of several staged-neutral outcomes before any further score, size, or window expansion
