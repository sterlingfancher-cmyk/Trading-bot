# Automated Trading Project Handoff — Updated July 30, 2026

## Engineering Constitution

1. Reliability before performance.
2. Evidence before modification.
3. Deterministic behavior before adaptive behavior.
4. Diagnostics before optimization.
5. Backtests do not replace live paper validation.
6. New capability must improve measurable performance without weakening hard risk controls.
7. Machine learning remains advisory until execution history, observed outcomes, out-of-sample evidence, and regime stability justify a stronger role.
8. Significant changes must be traceable, reversible, and validated before becoming the baseline.
9. No threshold, extension guard, risk control, or filter may be relaxed merely to force activity.
10. Runtime callable ownership must be deterministic; wrapper races and false ownership diagnostics are defects.

## Standing Rule

Every code or configuration update must update this handoff in the same work session with the evidence reviewed, files and versions changed, commits, routes, safety impact, validation state, and exact next action.

## Always Resume Here

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Branch: `main`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Operating mode: paper only.
- Live-trading authority: none.
- ML execution authority: none; advisory only.
- July 29 performance-risk, regime-integrity, bear-short recovery, and entry-pipeline ownership work is source-complete and Railway-validated.
- July 30 opening-surge strategy logic is source-complete.
- July 30 scanner-ownership v2 is committed; Railway validation of v2 is pending.
- Current entry stack remains:
  1. bear soft-pause short recovery;
  2. one Entry Pipeline X-Ray;
  3. deterministic breakout/composition callable;
  4. direct core entry pipeline.
- Current validated entry-wrapper counts: one bear wrapper and one X-Ray wrapper.
- Opening surge wraps `risk_parameters` and `scan_signals`; it does not replace `try_entries_and_rotations`.
- First endpoint after v2 redeploy:
  - `/paper/opening-surge-participation-status`
- Then verify:
  - `/paper/entry-pipeline-xray-bear-ownership-status`
  - `/paper/bear-recovery-stack-status`
  - `/paper/self-check`
- During the next eligible opening:
  - `/paper/opening-surge-participation-status`
  - `/paper/no-entry-diagnostic?force=1`
- Do not lower the `0.014` bear-recovery short floor, weaken hard loss limits, broadly enable defensive-regime longs, or enable live/ML authority.

## Executive Status

| Item | Current status |
|---|---|
| Account snapshot used in this sprint | Cash/equity about `$10,734.80`; no open exposure |
| Lifetime completed exits | 52 |
| Lifetime wins / losses | 35 / 17 |
| Lifetime win rate | `67.31%` |
| Lifetime net realized P&L | `+$734.82` |
| Lifetime profit factor | `3.1781` |
| Recent 20 exits | 15 wins / 5 losses; `+$681.29`; PF `3.4278` |
| Global opening warmup | 15 minutes |
| Opening-surge window | 15–45 minutes after the 08:30 CDT open |
| Opening-surge capacity | One reduced-size long per day; empty book only |
| Opening-surge minimum score | `0.045` |
| Opening-surge cluster | At least two independently qualifying leaders |
| Opening-surge NQ requirement | At least `+0.80%`, trend up |
| Confirmed-bear opening longs | Never allowed |
| Soft realized-loss pause | `1.00%` |
| Hard realized-loss halt | `2.50%` |
| Hard intraday-drawdown halt | `2.50%` |
| Absolute daily-loss ceiling | `3.00%` |
| Live authority | None |
| ML authority | Advisory only |

## July 29 Performance and Risk Calibration

The strategy record showed positive expectancy, so the work preserved the strategy and repaired underdeployment rather than replacing it.

Evidence:

- gross profit `$1,072.18`;
- gross loss `-$337.36`;
- net realized profit `+$734.82`;
- average win `$30.63`;
- average loss `-$19.84`;
- payoff ratio `1.5437`;
- expectancy `+$14.13` per completed exit;
- recent-20 expectancy `+$34.06`.

Active risk ladder:

- `1.00%` realized-loss soft pause;
- controlled restart only in explicitly eligible conditions;
- `2.50%` hard realized-loss halt;
- `2.50%` hard intraday-drawdown halt;
- `3.00%` absolute daily-loss ceiling;
- controlled-recovery sizing capped at 50%;
- no rotations during controlled recovery.

Files and commits:

- `performance_risk_calibration.py` — `838ec3b23a6e573177e1fd51dd2917e8adda4c25`
- `usercustomize.py` calibration registration — `c5a188597074ae8c83e59f78e6e11903b47a3ec4`
- `fast_self_check_override.py` — `1432b21dbd1d2725c1693da317ca7accd98f7746`
- `performance_risk_activation_guard.py` — `8dba35127a9656826020a5239bf146778628c5da`
- initial worker activation — `85d06eb45e476ba9d50a27ab1479f694984a5c6c`
- route: `/paper/performance-risk-activation-status`

## Regime Integrity and Underdeployment Repair

Root causes:

1. `risk_off` could disable longs while shorts remained unavailable because bear confirmation failed.
2. The macro request was too short to supply the minimum daily trend bars.
3. Market mode was assigned before all futures, breadth, and defensive adjustments.
4. A long-oriented soft-pause block globally prevented a valid confirmed-bear short sleeve.
5. Wrapper ownership sometimes displaced the active risk gate.

Implemented behavior:

- sufficient macro history;
- explicit macro bar counts;
- repaired SPY and QQQ trend states;
- five-day SPY, QQQ, VIX, and Treasury changes;
- auditable risk-score ledger;
- final mode, regime, and permission recomputed after overlays;
- shorts enabled only after all bear-confirmation tests;
- normal market-data cache preserved;
- no risk-off long exception added.

Railway evidence on July 29:

- SPY trend down;
- QQQ trend down;
- SPY five-day return `-1.97%`;
- QQQ five-day return `-5.77%`;
- VIX five-day change `+17.83%`;
- all five bear tests true;
- risk score `0`;
- mode `risk_off`;
- regime `bear`;
- permission `short_bias`;
- longs false;
- shorts true;
- prior neither-side dead zone removed.

Commits and routes:

- regime repair — `136f74a2078cf1b95b9f2a171a4b07c8e9e8cf56`
- startup registration — `a06d0020d640686a4de2894ed383ea3fe85051fd`
- cache preservation — `a713b04d8cf1910ccb71dfe51df396558c20704f`
- final activation — `0106e574973668a4dff4bed424653898fed33331`
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

Commits and route:

- policy — `599dcc98355eb9ba4c46920576d1c4eb26f4ecfe`
- activation — `4e4b27463d28652aae294ebd49c8976bfaa7b93d`
- `/paper/bear-short-recovery-status`

## Entry-Pipeline Ownership Repair

Required stack:

1. bear soft-pause short recovery;
2. one Entry Pipeline X-Ray;
3. breakout/composition guard;
4. direct core entry pipeline.

Observed defects included composition displacing bear recovery, duplicate bear wrappers, and duplicate X-Ray wrappers.

Repairs:

- `bear_recovery_stack_contract.py` v2 normalizes to one bear gate and one X-Ray.
- `entry_pipeline_xray_bear_ownership_guard.py` prevents X-Ray from wrapping above a valid bear-owned stack.
- recurring owner order ends with the bear stack contract.

Commits:

- initial contract — `61287a0b8dd6f89a073a17e11904a72723901340`
- initial registration — `0bc442df367e482fa3526a92d096db04f6be7bbb`
- duplicate-edge repair — `38a3c935c844716f11f12ab426573e3e83707cf7`
- v2 contract — `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring owner order — `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- X-Ray producer guard — `6589dd791c85575214af103df4414e678441daff`
- final registration — `8f071f172aec72273288abf92c50fd4697db1856`
- comprehensive July 29 handoff — `d677e1b7528c4869193730771d26cbf482918d9b`
- final July 29 validation handoff — `e1e70544fbdd4e368cacea068d268d3673f1ff10`

Railway validation at 12:36:08 and 12:37:41 CDT:

- ownership routes passed;
- `owned: true`;
- `entry_guard_active: true`;
- one bear wrapper;
- one X-Ray wrapper;
- composition and direct-core metadata present;
- no drift after a recurring repair interval.

The July 29 entry-pipeline ownership defect is closed.

## July 30 Morning Missed-Opening Investigation

At 09:08:52 CDT:

- market had been open 38.9 minutes;
- the 15-minute warmup was inactive;
- no risk halt, loss, drawdown, self-defense, or profit guard was active;
- scanner found 12 signals: six long and six short;
- mode was `crash_warning`, regime `bear`, risk score `14`;
- NQ was `+1.439%`, trend up, with `gap_chase_protection`;
- both `allow_longs` and `allow_shorts` were false;
- the primary no-entry driver was `longs_disabled_by_regime`.

High-score rejected longs included:

- AMD `0.066916`;
- ALAB `0.051672`;
- MU `0.050216`;
- ACLS `0.048229`;
- MRVL `0.039829`.

By 09:05, those leaders were recorded as `extended_above_5m_ma20`. The scanner saw the opportunity, but the regime permission layer kept the bot inactive until the ordinary no-chase layer considered the names too extended.

The supplied 09:09–09:11 charts showed:

- WDC `+15.95%`;
- CORZ `+22.35%`;
- CRWV `+18.65%`;
- LRCX `+20.32%`;
- NBIS `+26.70%`;
- SNDK `+18.45%`;
- RIOT `+19.87%`;
- AMD `+12.67%`;
- BE `+26.30%`;
- PWR `+15.64%`.

LRCX and PWR were below their opening prints despite large prior-close gains, confirming that the repair must require positive post-open follow-through rather than buying every gap.

Root cause:

- this was not a one-hour no-trade rule;
- the global warmup is 15 minutes;
- the macro label remained defensive while the current NQ/opening tape was strongly bullish;
- ordinary longs and the existing relative-strength exception were disabled in `crash_warning`;
- the best opening participation window passed before the normal scanner could safely act.

## Opening-Surge Participation Valve v1

File and commits:

- `opening_surge_participation.py`
- version `opening-surge-participation-2026-07-30-v1`
- source — `2351b9b70e22df414aba248abc5e60b03d477431`
- Gunicorn activation — `3ec95ac24b1eed95367a3fe74813895388cb1a27`
- initial July 30 handoff — `28e4fc462f1f93e3a9fa6bb25f8f654b04331671`
- route: `/paper/opening-surge-participation-status`

This is a bounded defensive-dislocation exception, not general defensive-regime long permission.

Permission requirements:

- paper context;
- regular session open;
- normal warmup complete;
- 15–45 minutes after open;
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
- move versus prior close between `+8%` and `+20%`;
- post-open follow-through between `+4%` and `+8%`;
- break above the first three five-minute bars;
- hold within 1.5% of session high;
- fast momentum hold;
- relative volume at least `1.25`, unless post-open move is at least 8%;
- approved leadership bucket.

At least two candidates must qualify. Up to three are promoted for ranking, but only one reduced-size opening-surge entry may be opened for the day.

Universe hints added:

- WDC, CORZ, CRWV, LRCX, NBIS, SNDK, RIOT, AMD, BE, PWR.

These hints do not make a symbol automatically tradable.

## Railway Validation of v1 and Scanner-Ownership Defect

At 09:46:58 CDT, Railway returned:

- version v1;
- `overall: pass`;
- risk guard active;
- scan guard active;
- the only permission blocker was `after_opening_surge_window`;
- NQ `+1.864%`, trend up;
- `bear_confirmed: false`;
- no loss or drawdown;
- empty book;
- one daily allowance remaining.

At 09:48:02 CDT, the entry stack remained passing:

- `owned: true`;
- `entry_guard_active: true`;
- one bear wrapper;
- one X-Ray wrapper;
- no drift;
- 42 scanner signals in the stored cycle.

At 09:57:13 CDT, a repeated opening-surge status returned:

- `overall: warn`;
- `risk_guard_active: true`;
- `scan_guard_active: false`;
- `last_install.scan_signals_patched_this_call: true` at 09:57:00;
- current status lost the outer scanner marker only 13 seconds later.

This proves the v1 outermost-only scanner ownership test is not stable. A metadata or diagnostic scanner wrapper can sit above the opening-surge wrapper while still calling through to it. V1 then reports a false displacement and rewraps again on the next watchdog pass, risking duplicate wrappers and misleading diagnostics.

## Opening-Surge Participation v2 — Chain-Aware Ownership

File and commit:

- `opening_surge_participation.py`
- version `opening-surge-participation-2026-07-30-v2-chain-aware`
- source commit — `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`
- route unchanged: `/paper/opening-surge-participation-status`
- no Gunicorn change required because the same module is already registered at worker startup.

V2 changes ownership semantics only; the strategy window, thresholds, candidate rules, sizing, and risk limits are unchanged.

Implemented behavior:

- bounded traversal of callable links such as `prior`, `original`, `wrapped`, `base`, and `inner`;
- explicit support for the known scanner instrumentation attributes;
- marker detection anywhere in the callable chain;
- no repeated rewrap when the opening-surge guard is nested but active;
- marker counts to detect duplicate opening-surge layers;
- cycle detection and bounded chain previews;
- separate `outermost` versus `nested_but_active` classifications;
- exact v2-version ownership checks;
- `__wrapped__` and explicit prior metadata on the new wrappers;
- chain-aware checks for both `scan_signals` and `risk_parameters`.

New status fields include:

- `scan_guard_outermost`;
- `scan_guard_count`;
- `scan_guard_depth`;
- `scan_classification`;
- `risk_guard_outermost`;
- `risk_guard_count`;
- `risk_guard_depth`;
- `risk_classification`;
- `ownership.scan.chain_preview`;
- `ownership.scan.cycle_detected`;
- `ownership.scan.first_match_path`.

Healthy v2 ownership requires exactly one matching risk guard and one matching scan guard. A guard may be nested beneath a reporting wrapper and still pass.

Source validation:

- v2 compiled successfully;
- simulated `metadata wrapper -> opening surge -> core scanner` was detected as `nested_but_active`;
- marker count was one;
- `_wrap_scan` became idempotent when the guard was nested;
- no strategy or hard-risk setting changed.

## Safety and Authority Boundary

Current work preserves:

- paper-only operation;
- no live broker authority;
- no ML execution authority;
- no direct order placement by the opening-surge module;
- no change to the `2.50%` hard realized-loss halt;
- no change to the `2.50%` hard intraday-drawdown halt;
- no change to the `3.00%` absolute daily-loss ceiling;
- no confirmed-bear long exception;
- no broad defensive-regime long permission;
- no relaxation of the ordinary extension guard;
- no change to the bear soft-pause short policy;
- no change to the validated entry-pipeline ownership stack.

The opening-surge module intentionally changes scanner supply, narrow strategy permission, and reduced opening sizing only during its bounded window.

## Validation Order After v2 Railway Deploy

### 1. Opening-surge ownership

`/paper/opening-surge-participation-status`

Expected after at least one recurring watchdog interval:

- version `opening-surge-participation-2026-07-30-v2-chain-aware`;
- `overall: pass`;
- `risk_guard_active: true`;
- `scan_guard_active: true`;
- `risk_guard_count: 1`;
- `scan_guard_count: 1`;
- `risk_classification` is `outermost` or `nested_but_active`;
- `scan_classification` is `outermost` or `nested_but_active`;
- `last_install.risk_parameters_patched_this_call: false`;
- `last_install.scan_signals_patched_this_call: false`;
- no ownership cycle;
- no duplicate classification.

Outside the 15–45 minute opening window, `permission_live.active: false` with `after_opening_surge_window` is normal.

### 2. Entry-stack regression

- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/bear-recovery-stack-status`

Expected:

- both pass;
- `owned: true`;
- `entry_guard_active: true`;
- one bear wrapper;
- one X-Ray wrapper.

### 3. Compact system check

- `/paper/self-check`

Use `/paper/full-self-check` only after a failed compact check, missing critical fields, a newly timestamped error, or an unexpected warning.

### 4. Next eligible market open

Between 08:45 and 09:15 CDT, inspect:

- `permission_live.active`;
- `last_scan.cluster_confirmed`;
- `last_scan.qualified_symbols`;
- `last_scan.promoted_symbols`;
- `/paper/no-entry-diagnostic?force=1`.

Determine whether a promoted candidate was accepted or blocked by normal core quality, timing, cooldown, position, risk, or execution controls.

## Previous Reliability Work Still in Force

- `run_report_guard.py` v2 — `d1915e5a79282d0f6ccd541c6024421cf8ad86cd`
- concurrent manual cycles must return `cycle_busy` rather than waiting for Gunicorn timeout;
- PR #6 merge — `9998c597ef91b5d6edce47cdf481efcb6ac4cc90`
- state provenance v2 — `9ce6ddc4e03c38a7c9c4f5e103c2fbbad7f0892b`
- missing-reason trace — `f42f4c985a7f1a7695c6cafdc46584ab379a63d8`
- missing-reason registration — `e0cbdd54775e2e6f17ced686b4e31e3f619d159f`

## Machine Learning Roadmap

ML remains advisory. Before any stronger role:

- decision, blocker, execution, position, and outcome records must remain joinable;
- feature and regime provenance must remain stable;
- labels must be complete and leakage-free;
- persistence must be trustworthy;
- at least 150 execution rows and 100 observed outcomes are required but not sufficient;
- train/validation/test and walk-forward evidence must show incremental value;
- shadow inference must run without decision authority.

Any ML influence over ranking, sizing, entry permission, or capital requires explicit approval.

## Definition of Done

Completed:

- July 29 performance-risk, regime, bear recovery, and entry-stack ownership repairs;
- repeated Railway entry-stack ownership validation;
- July 30 missed-opening evidence and root cause documented;
- bounded opening-surge strategy implemented;
- v1 Railway installation and entry-stack regression checks passed;
- repeated v1 status exposed scanner ownership instability;
- v2 chain-aware ownership implemented and source-tested;
- main handoff updated through the v2 commit.

Pending:

- Railway serves v2;
- exactly one v2 scan guard and one v2 risk guard remain discoverable after a recurring watchdog interval;
- entry ownership remains passing after v2;
- next eligible opening records actual cluster and promotion evidence;
- any accepted opening-surge entry remains one reduced-size position and clears the normal core pipeline.

## Next Action

After Railway deploys commit `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`, run `/paper/opening-surge-participation-status` twice, at least 60 seconds apart. Confirm one scan guard, one risk guard, no cycle, and a classification of `outermost` or `nested_but_active`. Then recheck the two entry-stack ownership routes and `/paper/self-check`. The actual candidate-to-entry path remains scheduled for the next eligible 08:45–09:15 CDT opening window.
