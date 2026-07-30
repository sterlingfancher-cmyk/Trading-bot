# Automated Trading Project Handoff — Canonical Status, July 30, 2026

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
10. Every code or configuration change and every major Railway validation milestone must update this handoff in the same work session.

## Always Resume Here

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Operating mode: paper only.
- Live-trading authority: none.
- ML execution authority: none; advisory only.
- Account snapshot used during this sprint: approximately `$10,734.80` cash/equity, no open exposure.
- Lifetime completed exits: 52 — 35 wins, 17 losses.
- Lifetime win rate: `67.31%`.
- Lifetime net realized P&L: `+$734.82`.
- Lifetime profit factor: `3.1781`.
- Recent 20 exits: 15 wins, 5 losses, `+$681.29`, PF `3.4278`.
- July 29 risk calibration, regime integrity, bear-short recovery, and entry-pipeline ownership work is Railway-validated.
- July 30 opening-surge strategy and chain-aware opening-surge ownership v2 are source-complete and Railway-validated.
- July 30 duplicate breakout-scanner ownership repair is now deployed and passed its first Railway validation at `2026-07-30 14:25:10 CDT`.
- Railway outage and Python artifact-attestation build failure are resolved by the root `mise.toml` build-only setting.
- Next operational milestone: validate real opening-surge candidate profiling and promotion during the next eligible `08:45–09:15 CDT` window.

## Current Hard Risk Ladder

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

## Validated Runtime Architecture

### Entry pipeline

Required and validated public stack:

1. `bear_soft_pause_short_recovery` — outer entry-risk owner;
2. one Entry Pipeline X-Ray wrapper;
3. deterministic breakout/composition callable;
4. direct core entry pipeline.

Validated state:

- `owned: true`;
- `entry_guard_active: true`;
- exactly one bear wrapper;
- exactly one X-Ray wrapper;
- direct-core and composition metadata present;
- no drift, recursion, or ownership oscillation.

### Scanner pipeline

Required and now validated scanner order:

1. `opening_surge_participation` wrapper;
2. exactly one `breakout_participation_layer` wrapper;
3. `market_participation_accelerator` and the remaining core scanner chain.

Railway evidence at `2026-07-30 14:25:10 CDT`:

- version `breakout-scanner-ownership-2026-07-30-v1`;
- `overall: pass`;
- `breakout_guard_count: 1`;
- `breakout_guard_depth: 1`;
- `opening_surge_guard_count: 1`;
- `opening_surge_guard_depth: 0`;
- `opening_surge_above_breakout: true`;
- `ownership.cycle_detected: false`;
- `ownership.truncated: false`;
- `ensure_breakout.patched: false` with reason `breakout_already_present`;
- `patcher_guard.patched: false` with reason `already_chain_guarded`;
- normalization removed zero wrappers because the deployed stack was already correct.

The prior duplicate-breakout scanner defect is closed at the first live validation. A repeated status sample after a watchdog interval should remain unchanged and is a persistence check, not a source-repair requirement.

## July 29 Performance and Risk Calibration

The strategy record showed positive expectancy, so the project preserved the strategy and repaired underdeployment, regime logic, risk governance, and callable ownership.

Evidence:

- gross profit `$1,072.18`;
- gross loss `-$337.36`;
- average win `$30.63`;
- average loss `-$19.84`;
- payoff ratio `1.5437`;
- lifetime expectancy `+$14.13` per completed exit;
- recent-20 expectancy `+$34.06`.

Key files and commits:

- `performance_risk_calibration.py` — `838ec3b23a6e573177e1fd51dd2917e8adda4c25`
- `usercustomize.py` calibration registration — `c5a188597074ae8c83e59f78e6e11903b47a3ec4`
- `fast_self_check_override.py` — `1432b21dbd1d2725c1693da317ca7accd98f7746`
- `performance_risk_activation_guard.py` — `8dba35127a9656826020a5239bf146778628c5da`
- worker activation — `85d06eb45e476ba9d50a27ab1479f694984a5c6c`
- route: `/paper/performance-risk-activation-status`

## Regime Integrity and Underdeployment Repair

Root causes repaired:

1. `risk_off` could disable longs while shorts remained unavailable because bear confirmation failed.
2. Macro history was too short to satisfy the daily-trend bar requirement.
3. Market mode was assigned before all futures, breadth, and defensive adjustments.
4. A long-oriented soft-pause block globally prevented a valid confirmed-bear short sleeve.
5. Runtime wrappers could displace the active authority layer.

Implemented behavior:

- sufficient SPY/QQQ macro history and explicit bar counts;
- rebuilt SPY and QQQ trend states;
- five-day SPY, QQQ, VIX, and Treasury-rate changes;
- auditable risk-score ledger;
- final mode, regime, and permission recomputed after all overlays;
- shorts enabled only after every bear-confirmation test passes;
- market-data cache preserved;
- no broad risk-off long exception.

Railway evidence on July 29:

- SPY and QQQ trends down;
- SPY five-day return `-1.97%`;
- QQQ five-day return `-5.77%`;
- VIX five-day change `+17.83%`;
- all five bear tests true;
- mode `risk_off`, regime `bear`, permission `short_bias`;
- longs false and shorts true;
- prior neither-side dead zone eliminated.

Commits and routes:

- regime repair — `136f74a2078cf1b95b9f2a171a4b07c8e9e8cf56`
- startup registration — `a06d0020d640686a4de2894ed383ea3fe85051fd`
- cache preservation — `a713b04d8cf1910ccb71dfe51df396558c20704f`
- final worker activation — `0106e574973668a4dff4bed424653898fed33331`
- `/paper/regime-integrity-status`
- `/paper/underdeployment-xray?force=1`

## Side-Aware Bear Soft-Pause Recovery

`bear_soft_pause_short_recovery.py` permits one reduced-size short only when:

- the soft pause is active;
- mode is `risk_off`;
- permission is `short_bias`;
- `bear_confirmed` is true;
- the regular session is open;
- no hard halt, late-day block, or profit guard is active;
- score is at least `0.014`;
- the daily recovery allowance remains unused.

The short uses at most a `0.50` allocation factor. Longs remain blocked and rotations remain disabled.

- policy — `599dcc98355eb9ba4c46920576d1c4eb26f4ecfe`
- worker activation — `4e4b27463d28652aae294ebd49c8976bfaa7b93d`
- route: `/paper/bear-short-recovery-status`

## Entry-Pipeline Ownership Repair

`bear_recovery_stack_contract.py` v2 normalizes to one bear gate and one X-Ray. `entry_pipeline_xray_bear_ownership_guard.py` prevents X-Ray from wrapping above an already valid bear-owned stack.

Key commits:

- initial contract — `61287a0b8dd6f89a073a17e11904a72723901340`
- initial registration — `0bc442df367e482fa3526a92d096db04f6be7bbb`
- duplicate-edge repair — `38a3c935c844716f11f12ab426573e3e83707cf7`
- v2 contract — `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring owner order — `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- X-Ray producer guard — `6589dd791c85575214af103df4414e678441daff`
- final registration — `8f071f172aec72273288abf92c50fd4697db1856`

Routes:

- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/bear-recovery-stack-status`

## July 30 Missed-Opening Investigation

At `09:08:52 CDT`:

- the market had been open 38.9 minutes;
- the normal 15-minute warmup had expired;
- no loss, drawdown, hard halt, self-defense, or profit-guard block was active;
- scanner found 12 signals, six long and six short;
- mode was `crash_warning`, regime `bear`, risk score `14`;
- NQ was `+1.439%`, trend up, with `gap_chase_protection`;
- both `allow_longs` and `allow_shorts` were false;
- the primary no-entry driver was `longs_disabled_by_regime`.

High-score longs later rejected as `extended_above_5m_ma20` included AMD `0.066916`, ALAB `0.051672`, MU `0.050216`, ACLS `0.048229`, and MRVL `0.039829`.

The supplied charts showed broad AI compute, semiconductor, crypto-compute, and power-infrastructure strength in WDC, CORZ, CRWV, LRCX, NBIS, SNDK, RIOT, AMD, BE, and PWR. LRCX and PWR were below their opening prints despite large prior-close gains, proving the strategy needed positive post-open follow-through rather than indiscriminate gap buying.

Root cause:

- this was not a one-hour no-trade rule;
- the global warmup is 15 minutes;
- defensive macro history conflicted with a strongly bullish current NQ/opening tape;
- ordinary longs and the prior relative-strength exception were disabled in `crash_warning`;
- the best opening participation window passed before the ordinary scanner could safely act.

## Opening-Surge Participation Valve

This is a bounded defensive-dislocation exception, not general defensive-regime long permission.

Permission requires:

- paper context and regular session open;
- normal warmup complete;
- 15–45 minutes after the `08:30 CDT` open;
- mode `crash_warning` or `risk_off`;
- `bear_confirmed` false;
- NQ at least `+0.80%`, trend up;
- bullish, bullish-but-extended, or gap-chase futures context;
- no hard halt, profit guard, self-defense, feedback hard halt, or global feedback block;
- daily loss and intraday drawdown each below `0.50%`;
- empty book;
- daily opening-surge allowance unused.

Candidate requirements:

- score at least `0.045`;
- prior-close move between `+8%` and `+20%`;
- post-open follow-through between `+4%` and `+8%`;
- break above the first three five-minute bars;
- hold within 1.5% of the session high;
- fast momentum hold;
- relative volume at least `1.25`, unless post-open move is at least 8%;
- approved leadership bucket.

At least two candidates must qualify in the same cycle. Up to three may be promoted, but only one reduced-size opening-surge entry is permitted per day. Maximum temporary long allocation supplied to the normal pipeline is 5% of equity before downstream factors.

Universe hints: WDC, CORZ, CRWV, LRCX, NBIS, SNDK, RIOT, AMD, BE, and PWR. Hints do not make a symbol automatically tradable.

Commits and route:

- v1 source — `2351b9b70e22df414aba248abc5e60b03d477431`
- v1 Gunicorn activation — `3ec95ac24b1eed95367a3fe74813895388cb1a27`
- v2 chain-aware ownership — `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`
- v2 version — `opening-surge-participation-2026-07-30-v2-chain-aware`
- route — `/paper/opening-surge-participation-status`

## Duplicate Breakout Scanner Repair

The opening-surge v2 chain preview exposed two breakout wrappers, one outside and one inside opening surge. The outer wrapper could repeat scanner work and append ordinary breakout signals after opening surge had filtered the long list.

Repair:

- `breakout_scanner_ownership_guard.py`;
- version `breakout-scanner-ownership-2026-07-30-v1`;
- source commit `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`;
- Gunicorn activation `115e921ecdfeb50fde4b4b1125787e9bb190352d`;
- route `/paper/breakout-scanner-ownership-status`.

The guard is chain-aware, refuses a new breakout wrapper when one already exists, removes only redundant outer breakout wrappers, preserves one breakout layer beneath opening surge, verifies ordering, and detects callable cycles or truncated ownership search.

Railway deployment and validation are now successful. The validated chain is:

```text
opening_surge_participation
  -> breakout_participation_layer
    -> market_participation_accelerator
```

## Railway Outage and Build Recovery

After Railway recovered from an outage, deployments failed before application startup because `mise` 2026.7.15 required a GitHub artifact attestation that was unavailable for the pinned Python 3.11.9 prebuilt package.

Observed error:

```text
mise python@3.11.9 verify GitHub artifact attestations
mise ERROR No GitHub artifact attestations found for python@3.11.9
```

Build-only repair:

- root file `mise.toml`;
- commit `4114e77163d921f50aa1d418f4ac709631738046`;
- setting:

```toml
[settings]
python.github_attestations = false
```

Python remains pinned at 3.11.9 through `runtime.txt`. No dependency, strategy, signal, threshold, sizing, risk, order, live-authority, or ML-authority behavior changed.

The successful breakout ownership response proves the build fix allowed the latest application revision to start and register the new route.

## Safety and Authority Boundary

Current work preserves:

- paper-only operation;
- no live broker authority;
- no ML execution authority;
- no direct order placement by ownership or build guards;
- no change to the `2.50%` hard realized-loss halt;
- no change to the `2.50%` hard intraday-drawdown halt;
- no change to the `3.00%` absolute daily-loss ceiling;
- no confirmed-bear opening long exception;
- no broad defensive-regime long permission;
- no relaxation of the ordinary extension guard;
- no change to the bear soft-pause short policy;
- no change to the validated entry-pipeline ownership stack.

## Validation Endpoints

- `/paper/breakout-scanner-ownership-status`
- `/paper/opening-surge-participation-status`
- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/bear-recovery-stack-status`
- `/paper/bear-short-recovery-status`
- `/paper/regime-integrity-status`
- `/paper/underdeployment-xray?force=1`
- `/paper/no-entry-diagnostic?force=1`
- `/paper/self-check`
- `/paper/full-self-check` only when compact checks fail or omit necessary evidence.

## Definition of Done

Completed:

- July 29 performance-risk, regime, bear recovery, and entry-stack ownership repairs;
- repeated Railway entry-stack validation;
- July 30 missed-opening evidence and root cause documented;
- bounded opening-surge strategy implemented;
- opening-surge v2 chain-aware ownership deployed and validated;
- duplicate breakout wrapper defect identified, repaired, deployed, and live-validated;
- Railway outage and deployment lag documented;
- Python 3.11.9 `mise` attestation build failure diagnosed and repaired;
- canonical handoff updated through the successful breakout-scanner ownership validation.

Pending:

- repeat `/paper/breakout-scanner-ownership-status` after a watchdog interval to confirm persistence with the same one-and-one wrapper counts;
- recheck `/paper/opening-surge-participation-status`, `/paper/bear-recovery-stack-status`, and `/paper/self-check` after the final deployment;
- during the next eligible `08:45–09:15 CDT` opening, capture real opening-surge `permission_live`, cluster, qualified-symbol, promoted-symbol, and downstream entry/rejection evidence;
- any accepted opening-surge entry must remain one reduced-size paper position and pass the normal core pipeline.

## Exact Next Action

Run `/paper/breakout-scanner-ownership-status` again after at least one watchdog interval. It should remain `overall: pass` with one opening-surge guard, one breakout guard, opening surge above breakout, and no cycle or truncation. Then run `/paper/opening-surge-participation-status`, `/paper/bear-recovery-stack-status`, and `/paper/self-check`. The next strategy-validation milestone is the next eligible opening-surge window, not another threshold or risk change.
