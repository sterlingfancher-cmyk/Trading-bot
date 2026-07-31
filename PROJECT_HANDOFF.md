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
- July 30 opening-surge ownership and breakout-scanner ownership are Railway-validated.
- July 31 opening-surge score calibration is source-complete and awaiting Railway validation.
- Next endpoint after deployment: `/paper/opening-surge-score-calibration-status`.
- Next strategy milestone: capture a real `08:45–09:15 CDT` opening cycle after the calibration deployment.

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

1. `opening_surge_participation`
2. exactly one `breakout_participation_layer`
3. `market_participation_accelerator`
4. remaining scanner chain

Railway evidence on July 30:

- `breakout-scanner-ownership-2026-07-30-v1`
- `overall: pass`
- one opening-surge guard
- one breakout guard
- opening surge above breakout
- no callable cycle
- no truncated ownership search
- no repair required on the validated call

## Performance and Risk Calibration

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

Repairs completed:

- sufficient SPY/QQQ macro history and explicit bar counts
- rebuilt SPY and QQQ trend states
- auditable risk-score ledger
- final mode and permission recomputed after all overlays
- shorts enabled only after all bear-confirmation tests
- market-data cache preserved
- no broad risk-off long exception

Key commits:

- regime repair — `136f74a2078cf1b95b9f2a171a4b07c8e9e8cf56`
- startup registration — `a06d0020d640686a4de2894ed383ea3fe85051fd`
- cache preservation — `a713b04d8cf1910ccb71dfe51df396558c20704f`
- final activation — `0106e574973668a4dff4bed424653898fed33331`

Bear soft-pause recovery:

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

Entry-stack commits:

- initial contract — `61287a0b8dd6f89a073a17e11904a72723901340`
- registration — `0bc442df367e482fa3526a92d096db04f6be7bbb`
- duplicate edge repair — `38a3c935c844716f11f12ab426573e3e83707cf7`
- v2 contract — `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring owner order — `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- X-Ray producer guard — `6589dd791c85575214af103df4414e678441daff`
- final registration — `8f071f172aec72273288abf92c50fd4697db1856`

Opening-surge ownership:

- v1 source — `2351b9b70e22df414aba248abc5e60b03d477431`
- v1 activation — `3ec95ac24b1eed95367a3fe74813895388cb1a27`
- v2 chain-aware ownership — `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`

Breakout scanner ownership:

- source — `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`
- activation — `115e921ecdfeb50fde4b4b1125787e9bb190352d`
- final live validation handoff — `3541f8cc2898d1f7364832910a1cbd0338a8afd4`

## Railway Build Recovery

Railway's `mise` release rejected the pinned Python 3.11.9 prebuilt artifact because no GitHub attestation was available.

Repair:

- `mise.toml`
- commit `4114e77163d921f50aa1d418f4ac709631738046`

```toml
[settings]
python.github_attestations = false
```

Python remains pinned to 3.11.9. This was build-only and changed no strategy, dependency, signal, threshold, sizing, risk, order, live, or ML authority behavior.

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

The opening-surge valve was created to allow one tightly bounded paper long when current opening tape strongly contradicted a defensive historical label.

## July 31 Opening-Surge Calibration Evidence

At `08:51:09 CDT`, 21.09 minutes after the open:

- opening-surge permission was active
- `bear_confirmed: false`
- NQ futures `+3.898%`, trend up
- ES futures `+1.662%`, trend up
- empty book
- no loss or drawdown
- one daily opening-surge allowance remaining
- market mode `risk_off`

However:

- `cluster_confirmed: false`
- zero qualified names
- zero promoted names
- every stored profile stopped at `score_below_opening_surge_floor`
- top raw scores were BWXT `0.021164`, BE `0.019536`, CVX `0.017632`, HWM `0.017491`, STX `0.016840`, and DELL `0.016539`
- the fixed raw floor was `0.045`

Root cause:

The same `0.045` value was being used as both:

1. a pre-profile screening threshold; and
2. the effective promoted score.

This short-circuited intraday analysis. Candidates never reached the existing gap, follow-through, opening-range, near-high, momentum, volume, and bucket tests.

The later `10:31:21 CDT` cycle found 28 signals but remained in a deliberate `risk_off` neither-side state. That midday policy was not changed in this calibration. The evidence-supported defect was the opening valve's raw-score short circuit.

## July 31 Two-Stage Opening Score Calibration

New file:

- `opening_surge_score_calibration.py`
- version `opening-surge-score-calibration-2026-07-31-v1`
- source commit `faf6fab8416c14b5e753b0f909edbebe963bdcac`
- Gunicorn activation `747a737848de7562035c44507ab81abe694cd11e`
- route `/paper/opening-surge-score-calibration-status`

Behavior:

- raw profile prefilter becomes `0.012`
- existing opening window remains 15–45 minutes
- existing permission requirements remain unchanged
- existing gap, follow-through, opening-range, near-high, momentum, relative-volume, bucket, and cluster tests remain unchanged
- candidates that fail structure are not promoted
- fully structure-confirmed candidates receive an auditable composite score
- final promoted score floor remains `0.045`
- final composite score is capped at `0.080`
- normal core ranking, quality, cooldown, position, risk, and execution controls remain downstream
- one reduced-size paper position per day remains the maximum
- no direct orders
- no live or ML authority
- no hard-risk change
- no confirmed-bear long exception

Composite ledger:

- raw scanner score
- structure confirmation credit
- excess prior-close move bonus
- excess post-open follow-through bonus
- relative-volume bonus
- calculated score
- adjusted promoted score

This is not a blanket threshold reduction. It separates candidate profiling from final tradability.

## Validation Endpoints

Primary post-deploy:

- `/paper/opening-surge-score-calibration-status`

Then:

- `/paper/opening-surge-participation-status`
- `/paper/breakout-scanner-ownership-status`
- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/bear-recovery-stack-status`
- `/paper/self-check`

During the next eligible opening:

- `/paper/opening-surge-participation-status`
- `/paper/opening-surge-score-calibration-status`
- `/paper/no-entry-diagnostic?force=1`

Other routes:

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
- two-stage score calibration source and startup wiring

Pending:

- Railway serves `opening-surge-score-calibration-2026-07-31-v1`
- calibration endpoint passes
- opening-surge and scanner ownership routes remain passing
- next eligible opening profiles candidates with raw scores at or above `0.012`
- at least two names must still pass every structure test before promotion
- any accepted position remains one reduced-size paper entry and clears the normal core pipeline
- collect real outcome evidence before any further permission, threshold, or sizing expansion

## Exact Next Action

After Railway deploys commits `faf6fab8416c14b5e753b0f909edbebe963bdcac` and `747a737848de7562035c44507ab81abe694cd11e`, run:

`https://trading-bot-clean.up.railway.app/paper/opening-surge-score-calibration-status`

Expected:

- version `opening-surge-score-calibration-2026-07-31-v1`
- `overall: pass`
- `active: true`
- `settings.profile_prefilter_score: 0.012`
- `settings.final_structure_score_floor: 0.045`
- existing structure tests, cluster requirement, and opening window unchanged

Then recheck opening-surge ownership, breakout-scanner ownership, entry ownership, and compact self-check. The actual candidate-to-entry validation must occur during the next `08:45–09:15 CDT` opening window.
