# Automated Trading Project Handoff — Canonical Status, July 31, 2026

## Engineering Constitution

1. Reliability before performance.
2. Evidence before modification.
3. Deterministic runtime ownership before adaptive behavior.
4. Diagnostics before optimization.
5. Backtests do not replace live paper validation.
6. Do not weaken hard risk controls or extension protection merely to force activity.
7. Machine learning remains advisory until execution history, outcome labels, out-of-sample evidence, and regime stability justify a stronger role.
8. Every material change must be traceable, reversible, source-tested, and Railway-validated before becoming the baseline.
9. Competing wrappers, duplicate callables, recursive patch chains, and false ownership warnings are defects.
10. Every code/configuration change and major Railway validation milestone must update this handoff in the same work session.

## Always Resume Here

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Operating mode: paper only.
- Live-trading authority: none.
- ML execution authority: none; advisory only.
- Current account snapshot: approximately `$10,734.80` cash/equity, no open exposure.
- Lifetime completed exits: 52 — 35 wins, 17 losses.
- Lifetime win rate: `67.31%`.
- Lifetime net realized P&L: `+$734.82`.
- Lifetime profit factor: `3.1781`.
- Recent 20 exits: 15 wins, 5 losses, `+$681.29`, PF `3.4278`.
- July 29 risk calibration, regime integrity, bear-short recovery, and entry ownership are Railway-validated.
- July 30 opening-surge and breakout-scanner ownership are Railway-validated.
- July 31 two-stage opening-surge score calibration is deployed, installation-validated, and post-deploy regression-validated.
- No additional threshold, permission, sizing, or risk change is authorized from the July 31 midday sample.
- Next strategy milestone: capture the first real calibrated opening cycle during the next eligible `08:45–09:15 CDT` window.

## Hard Risk Ladder

- Realized-loss soft pause: `1.00%`.
- Hard realized-loss halt: `2.50%`.
- Hard intraday-drawdown halt: `2.50%`.
- Absolute daily-loss ceiling: `3.00%`.
- Controlled-recovery sizing cap: 50%.
- No rotations during controlled recovery.
- Opening-surge temporary loss/drawdown ceiling: `0.50%`.
- Bear soft-pause short score floor: `0.014`.
- No confirmed-bear opening long exception.
- No broad defensive-regime long permission.
- Opening-surge maximum: one reduced-size paper position, empty book only.

## Validated Runtime Architecture

### Entry pipeline

Required order:

1. `bear_soft_pause_short_recovery`
2. one Entry Pipeline X-Ray
3. deterministic breakout/composition callable
4. direct core entry pipeline

Validated state:

- `owned: true`
- `entry_guard_active: true`
- exactly one bear wrapper
- exactly one X-Ray wrapper
- no drift, recursion, or ownership oscillation

### Scanner pipeline

Required order:

1. `opening_surge_participation`
2. exactly one `breakout_participation_layer`
3. `market_participation_accelerator`
4. remaining scanner chain

Validated state:

- one opening-surge guard
- one breakout guard
- opening surge above breakout
- no callable cycle
- no truncated ownership search
- no repair required on the validated calls

## Performance Record and Risk Calibration

The strategy record showed positive expectancy, so the project preserved the strategy and repaired underdeployment rather than replacing it.

Evidence:

- gross profit `$1,072.18`
- gross loss `-$337.36`
- average win `$30.63`
- average loss `-$19.84`
- payoff ratio `1.5437`
- lifetime expectancy `+$14.13` per completed exit
- recent-20 expectancy `+$34.06`

Core commits:

- `performance_risk_calibration.py` — `838ec3b23a6e573177e1fd51dd2917e8adda4c25`
- `usercustomize.py` registration — `c5a188597074ae8c83e59f78e6e11903b47a3ec4`
- `fast_self_check_override.py` — `1432b21dbd1d2725c1693da317ca7accd98f7746`
- `performance_risk_activation_guard.py` — `8dba35127a9656826020a5239bf146778628c5da`
- worker activation — `85d06eb45e476ba9d50a27ab1479f694984a5c6c`

## Regime Integrity and Bear Recovery

Completed repairs:

- sufficient SPY/QQQ macro history and explicit bar counts
- rebuilt SPY and QQQ trend states
- auditable risk-score ledger
- final mode and permission recomputed after overlays
- shorts enabled only after all bear-confirmation tests
- market-data cache preserved
- no broad risk-off long exception

Key commits:

- regime repair — `136f74a2078cf1b95b9f2a171a4b07c8e9e8cf56`
- startup registration — `a06d0020d640686a4de2894ed383ea3fe85051fd`
- cache preservation — `a713b04d8cf1910ccb71dfe51df396558c20704f`
- final activation — `0106e574973668a4dff4bed424653898fed33331`

Bear soft-pause recovery remains:

- one reduced-size short only
- `risk_off`
- `short_bias`
- `bear_confirmed`
- score at least `0.014`
- regular session open
- no hard halt, late-day block, or profit guard
- maximum `0.50` allocation factor
- longs remain blocked; rotations disabled

Commits:

- policy — `599dcc98355eb9ba4c46920576d1c4eb26f4ecfe`
- activation — `4e4b27463d28652aae294ebd49c8976bfaa7b93d`

## Entry and Scanner Ownership Repairs

Entry stack:

- initial contract — `61287a0b8dd6f89a073a17e11904a72723901340`
- registration — `0bc442df367e482fa3526a92d096db04f6be7bbb`
- duplicate-edge repair — `38a3c935c844716f11f12ab426573e3e83707cf7`
- v2 contract — `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring owner order — `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- X-Ray producer guard — `6589dd791c85575214af103df4414e678441daff`
- final registration — `8f071f172aec72273288abf92c50fd4697db1856`

Opening surge:

- v1 source — `2351b9b70e22df414aba248abc5e60b03d477431`
- v1 activation — `3ec95ac24b1eed95367a3fe74813895388cb1a27`
- v2 chain-aware ownership — `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`

Breakout scanner:

- ownership guard — `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`
- worker activation — `115e921ecdfeb50fde4b4b1125787e9bb190352d`
- live validation handoff — `3541f8cc2898d1f7364832910a1cbd0338a8afd4`

## Railway Build Recovery

Railway's `mise` release rejected the pinned Python 3.11.9 artifact because no GitHub attestation was available.

Repair:

- root `mise.toml`
- commit `4114e77163d921f50aa1d418f4ac709631738046`

```toml
[settings]
python.github_attestations = false
```

Python remains pinned to 3.11.9. This changed no dependency, strategy, signal, threshold, sizing, risk, order, live, or ML authority behavior.

## July 30 Missed-Opening Evidence

At `09:08:52 CDT`:

- normal 15-minute warmup had expired
- no loss, drawdown, hard halt, self-defense, or profit guard
- 12 signals: six long and six short
- mode `crash_warning`, regime `bear`, risk score `14`
- NQ `+1.439%`, trend up
- both long and short permissions false
- primary no-entry driver `longs_disabled_by_regime`

High-score names later labeled extended included AMD `0.066916`, ALAB `0.051672`, MU `0.050216`, ACLS `0.048229`, and MRVL `0.039829`.

The opening-surge valve was created to permit one tightly bounded paper long when the opening tape strongly contradicts a defensive historical label.

## July 31 Raw-Score Short-Circuit Evidence

At `08:51:09 CDT`, 21.09 minutes after the open:

- opening-surge permission active
- `bear_confirmed: false`
- NQ `+3.898%`, trend up
- ES `+1.662%`, trend up
- empty book
- no loss or drawdown
- one opening allowance remaining
- market mode `risk_off`

But:

- `cluster_confirmed: false`
- zero qualified names
- zero promoted names
- every profile stopped at `score_below_opening_surge_floor`
- top raw scores: BWXT `0.021164`, BE `0.019536`, CVX `0.017632`, HWM `0.017491`, STX `0.016840`, DELL `0.016539`
- fixed raw floor was `0.045`

Root cause:

The same `0.045` value was used as both a pre-profile screen and the promoted score. Candidates never reached the existing gap, follow-through, opening-range, near-high, momentum, volume, and bucket tests.

## July 31 Two-Stage Opening Score Calibration

File and commits:

- `opening_surge_score_calibration.py`
- version `opening-surge-score-calibration-2026-07-31-v1`
- source — `faf6fab8416c14b5e753b0f909edbebe963bdcac`
- Gunicorn activation — `747a737848de7562035c44507ab81abe694cd11e`
- initial calibration handoff — `2bee3f71e6d638c0e1dfd2b19077866af350222c`
- route — `/paper/opening-surge-score-calibration-status`

Behavior:

- raw profile prefilter `0.012`
- final structure score floor `0.045`
- final score cap `0.080`
- structure base credit `0.018`
- opening window remains 15–45 minutes
- permission requirements unchanged
- gap, follow-through, opening-range, near-high, momentum, volume, bucket, and cluster tests unchanged
- structurally failed candidates are not promoted
- normal core ranking, quality, cooldown, position, risk, and execution controls remain downstream
- one reduced-size paper position remains the daily maximum
- no direct orders, live authority, ML authority, hard-risk change, or confirmed-bear long exception

Composite ledger:

- raw scanner score
- structure confirmation credit
- excess prior-close move bonus
- excess post-open follow-through bonus
- relative-volume bonus
- calculated score
- adjusted promoted score

This is a profiling calibration, not a blanket entry-threshold reduction.

## Railway Calibration Validation — July 31, 10:48:54 CDT

The calibration endpoint returned:

- `overall: pass`
- `active: true`
- `patched_this_call: false`
- profile prefilter `0.012`
- final floor `0.045`
- cap `0.080`
- structure credit `0.018`
- existing structure tests, cluster requirement, and opening window unchanged
- paper-only authority preserved

`last_profile` was empty because deployment occurred after the opening window. This is expected.

## Post-Calibration Regression Validation — July 31, 10:54–10:55 CDT

### Opening-surge ownership

- `overall: pass`
- version `opening-surge-participation-2026-07-30-v2-chain-aware`
- one risk guard at depth zero
- one scan guard at depth zero
- both classified `outermost`
- no patching on the current call
- no cycle or truncation
- runtime setting `minimum_score: 0.012`
- inactive permission was correct because the window had ended and NQ trend was flat

The visible `stored_state` remained the pre-calibration `08:51:09` snapshot with `score_below_opening_surge_floor` reasons. The new worker's in-memory `last_scan` was empty because it deployed after the opening window. The old stored snapshot is historical evidence and does not indicate that the calibrated prefilter failed.

### Breakout scanner ownership

- `overall: pass`
- one opening-surge guard at depth zero
- one breakout guard at depth one
- opening surge above breakout
- no cycle or truncation
- no normalization required
- no patch required; breakout already present and chain-guarded

### Entry-stack ownership

- `overall: pass`
- `owned: true`
- `entry_guard_active: true`
- one bear wrapper
- one X-Ray wrapper
- known wrapper depth three
- no drift, repair, recursion, or logic change

### Compact self-check

- `overall: pass`
- auto-runner enabled at 300-second cadence
- last successful automatic cycle `10:55:17 CDT`
- no auto-runner error
- scanner found 62 signals
- zero entries
- no entry-pipeline recursion
- no realized loss or drawdown
- no risk halt or self-defense activation
- account remained flat at approximately `$10,734.80`

Interpretation:

The calibration deployment did not destabilize scanner ownership, entry ownership, the auto-runner, or the hard-risk ladder. The 62-signal midday count is not evidence that a trade should have occurred: the system remained in `risk_off`, the bounded opening window was closed, and this release intentionally did not broaden midday permissions.

## Validation Endpoints

During the next eligible opening:

- `/paper/opening-surge-participation-status`
- `/paper/opening-surge-score-calibration-status`
- `/paper/no-entry-diagnostic?force=1`

Regression and operations:

- `/paper/breakout-scanner-ownership-status`
- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/bear-recovery-stack-status`
- `/paper/self-check`
- `/paper/bear-short-recovery-status`
- `/paper/regime-integrity-status`
- `/paper/underdeployment-xray?force=1`
- `/paper/full-self-check` only when compact checks fail or omit required evidence

## Definition of Done

Completed:

- July 29 risk, regime, bear recovery, and entry ownership repairs
- July 30 missed-opening diagnosis
- bounded opening-surge permission
- chain-aware opening-surge ownership
- duplicate breakout scanner repair and live validation
- Railway Python attestation build recovery
- July 31 raw-score short-circuit diagnosis
- two-stage score calibration source, startup wiring, deployment, installation validation, and post-deploy regression validation

Pending:

- first eligible opening after calibration profiles candidates with raw scores at or above `0.012`
- at least two names must pass every existing structure test before promotion
- inspect the composite score ledger for any qualified name
- determine whether the normal core pipeline accepts or rejects promoted candidates
- any accepted position remains one reduced-size paper entry
- collect real outcome evidence before further permission, threshold, or sizing expansion

## Exact Next Action

Do not make another strategy change from the July 31 midday sample.

During the next `08:45–09:15 CDT` opening window, inspect:

1. `/paper/opening-surge-participation-status`
2. `/paper/opening-surge-score-calibration-status`
3. `/paper/no-entry-diagnostic?force=1`

Confirm that candidates with raw scores at or above `0.012` reach full structure profiling. Promotion still requires a two-name structurally confirmed cluster, and any entry must pass the normal core pipeline and remain one reduced-size paper position.