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
10. Every code or configuration change must update this handoff in the same work session.

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
- July 29 risk calibration, regime integrity, bear-short recovery, and entry-pipeline ownership repairs are Railway-validated.
- July 30 opening-surge strategy and chain-aware ownership v2 are deployed and initially Railway-validated.
- One final scanner-composition defect was exposed by the v2 chain preview: duplicate breakout-participation wrappers.
- Breakout scanner ownership guard source and worker activation are committed; Railway validation is pending.

## Current Hard Risk Ladder

- Realized-loss soft pause: `1.00%`.
- Hard realized-loss halt: `2.50%`.
- Hard intraday-drawdown halt: `2.50%`.
- Absolute daily-loss ceiling: `3.00%`.
- Controlled-recovery sizing cap: 50%.
- No rotations during controlled recovery.
- Opening-surge temporary loss/drawdown ceiling: `0.50%`.
- No confirmed-bear opening long exception.
- Bear soft-pause short score floor remains `0.014`.

## July 29 Performance and Risk Calibration

The strategy record showed positive expectancy rather than a strategy-quality collapse. The response was to preserve the strategy and repair underdeployment, regime logic, risk governance, and callable ownership.

Evidence:

- gross profit `$1,072.18`;
- gross loss `-$337.36`;
- average win `$30.63`;
- average loss `-$19.84`;
- payoff ratio `1.5437`;
- lifetime expectancy `+$14.13` per completed exit;
- recent-20 expectancy `+$34.06`.

Files and commits:

- `performance_risk_calibration.py` — `838ec3b23a6e573177e1fd51dd2917e8adda4c25`
- `usercustomize.py` calibration registration — `c5a188597074ae8c83e59f78e6e11903b47a3ec4`
- `fast_self_check_override.py` — `1432b21dbd1d2725c1693da317ca7accd98f7746`
- `performance_risk_activation_guard.py` — `8dba35127a9656826020a5239bf146778628c5da`
- worker activation — `85d06eb45e476ba9d50a27ab1479f694984a5c6c`
- route: `/paper/performance-risk-activation-status`

## Regime Integrity and Underdeployment Repair

Root causes repaired:

1. `risk_off` could disable longs while shorts were unavailable because bear confirmation failed.
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

Required entry stack:

1. bear soft-pause short recovery;
2. one Entry Pipeline X-Ray;
3. breakout/composition callable;
4. direct core entry pipeline.

`bear_recovery_stack_contract.py` v2 normalizes to one bear gate and one X-Ray. `entry_pipeline_xray_bear_ownership_guard.py` prevents X-Ray from wrapping above an already valid bear-owned stack.

Key commits:

- initial contract — `61287a0b8dd6f89a073a17e11904a72723901340`
- duplicate-edge repair — `38a3c935c844716f11f12ab426573e3e83707cf7`
- v2 contract — `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring owner order — `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- X-Ray producer guard — `6589dd791c85575214af103df4414e678441daff`
- final registration — `8f071f172aec72273288abf92c50fd4697db1856`

Railway passed at 12:36:08 and 12:37:41 CDT on July 29, and again at 10:44:24 CDT on July 30:

- `owned: true`;
- `entry_guard_active: true`;
- exactly one bear wrapper;
- exactly one X-Ray wrapper;
- direct-core and composition metadata present;
- no drift, recursion, or repair loop.

The entry-pipeline ownership defect is closed.

## July 30 Missed-Opening Investigation

At 09:08:52 CDT:

- the market had been open 38.9 minutes;
- the normal 15-minute warmup had expired;
- there was no loss, drawdown, hard halt, self-defense, or profit-guard block;
- scanner found 12 signals, six long and six short;
- mode was `crash_warning`, regime `bear`, risk score `14`;
- NQ was `+1.439%`, trend up, with `gap_chase_protection`;
- both `allow_longs` and `allow_shorts` were false;
- the primary no-entry driver was `longs_disabled_by_regime`.

High-score long examples rejected as `extended_above_5m_ma20` included AMD `0.066916`, ALAB `0.051672`, MU `0.050216`, ACLS `0.048229`, and MRVL `0.039829`.

The supplied charts showed broad AI compute, semiconductor, crypto-compute, and power-infrastructure strength, including WDC, CORZ, CRWV, LRCX, NBIS, SNDK, RIOT, AMD, BE, and PWR. LRCX and PWR were below their opening prints despite large prior-close gains, proving the repair needed positive post-open follow-through rather than indiscriminate gap buying.

Root cause:

- this was not a one-hour no-trade rule;
- the global warmup is 15 minutes;
- defensive macro history conflicted with a strongly bullish current NQ/opening tape;
- ordinary longs and the prior relative-strength exception were disabled in `crash_warning`;
- the best opening participation window passed before the ordinary scanner could safely act.

## Opening-Surge Participation Valve

### Strategy design

This is a bounded defensive-dislocation exception, not general defensive-regime long permission.

Permission requires:

- paper context and regular session open;
- normal warmup complete;
- 15–45 minutes after the 08:30 CDT open;
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

At least two candidates must qualify in the same cycle. Up to three candidates may be promoted, but the risk layer permits only one reduced-size opening-surge entry per day. Maximum temporary long allocation supplied to the normal pipeline is 5% of equity before downstream factors.

Universe hints added: WDC, CORZ, CRWV, LRCX, NBIS, SNDK, RIOT, AMD, BE, and PWR. Hints do not make a symbol automatically tradable.

### V1 and v2 commits

- v1 source — `2351b9b70e22df414aba248abc5e60b03d477431`
- v1 Gunicorn activation — `3ec95ac24b1eed95367a3fe74813895388cb1a27`
- v2 chain-aware ownership — `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7`
- v2 version: `opening-surge-participation-2026-07-30-v2-chain-aware`
- route: `/paper/opening-surge-participation-status`

V2 changes ownership inspection only. The strategy window, thresholds, sizing, candidate rules, and hard-risk limits are unchanged.

### Railway v2 evidence at 10:45:07 CDT

The v2 opening-surge route passed:

- `overall: pass`;
- risk guard active, outermost, count `1`, depth `0`;
- scan guard active, count `1`, depth `1`;
- scan classification `nested_but_active`;
- `risk_parameters_patched_this_call: false`;
- `scan_signals_patched_this_call: false`;
- no callable cycle;
- no truncated ownership search.

The scan path was:

1. outer `breakout_participation_layer.patched_scan_signals`;
2. opening-surge v2 wrapper;
3. another `breakout_participation_layer.patched_scan_signals`;
4. market-participation scanner.

Opening-surge v2 correctly recognized itself as nested and stopped rewrapping. Permission was correctly inactive because the system was after the opening window, `bear_confirmed` was true, and NQ/ES intraday trends were down.

## Duplicate Breakout Scanner Defect and Repair

The v2 chain preview exposed two breakout-participation wrappers. This is a separate outermost-only ownership defect in `breakout_participation_layer._patch_scan_signals`.

Why it matters:

- duplicate breakout wrappers repeat scanner work and market-data calls;
- the outer breakout wrapper can append ordinary breakout longs after opening surge has deliberately filtered the long list to opening-surge candidates;
- that ordering could weaken the narrow `opening_surge_only` contract even though hard risk controls remain downstream.

Repair:

- new file: `breakout_scanner_ownership_guard.py`;
- version: `breakout-scanner-ownership-2026-07-30-v1`;
- source commit: `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43`;
- Gunicorn activation: `115e921ecdfeb50fde4b4b1125787e9bb190352d`;
- route: `/paper/breakout-scanner-ownership-status`.

The guard:

- makes the breakout patcher chain-aware;
- refuses a new breakout wrapper when one already exists anywhere in the callable chain;
- removes only redundant outer breakout wrappers;
- preserves one breakout layer beneath the opening-surge filter;
- requires one opening-surge guard and one breakout guard;
- verifies opening surge is above breakout in the scanner chain;
- detects callable cycles and bounded-search truncation;
- runs a recurring ownership watchdog.

Source validation completed:

- module compiles;
- simulated `breakout outer -> opening surge -> breakout inner -> core` normalized to `opening surge -> breakout -> core`;
- final breakout count was one;
- final opening-surge count was one;
- opening surge remained above breakout;
- no strategy threshold, signal criterion, sizing rule, hard-risk limit, live authority, or ML authority changed.

## Safety and Authority Boundary

Current work preserves:

- paper-only operation;
- no live broker authority;
- no ML execution authority;
- no direct order placement by the ownership guards;
- no change to the `2.50%` hard realized-loss halt;
- no change to the `2.50%` hard intraday-drawdown halt;
- no change to the `3.00%` absolute daily-loss ceiling;
- no confirmed-bear opening long exception;
- no broad defensive-regime long permission;
- no relaxation of the ordinary extension guard;
- no change to the bear soft-pause short policy;
- no change to the validated entry-pipeline ownership stack.

## Post-Deploy Validation Order

### 1. Breakout scanner ownership

`/paper/breakout-scanner-ownership-status`

Expected after Railway deploys `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43` and `115e921ecdfeb50fde4b4b1125787e9bb190352d`:

- version `breakout-scanner-ownership-2026-07-30-v1`;
- `overall: pass`;
- `breakout_guard_count: 1`;
- `opening_surge_guard_count: 1`;
- `opening_surge_above_breakout: true`;
- `ownership.cycle_detected: false`;
- `ownership.truncated: false`.

The first run may report one redundant outer wrapper removed. Subsequent runs should report no new removal or rewrapping.

### 2. Opening-surge ownership

`/paper/opening-surge-participation-status`

Expected:

- v2 version;
- `overall: pass`;
- one risk guard;
- one scan guard;
- no callable cycle;
- no patch on the current call;
- classification `outermost` or `nested_but_active`.

Outside the 15–45 minute window, inactive permission is normal.

### 3. Entry-stack regression

- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/bear-recovery-stack-status`

Expected: both pass, `owned: true`, one bear wrapper, one X-Ray wrapper, and no drift.

### 4. Compact system check

- `/paper/self-check`

Use `/paper/full-self-check` only after a failed compact check, missing critical fields, a newly timestamped error, or an unexpected warning.

### 5. Next eligible market open

Between 08:45 and 09:15 CDT inspect:

- opening-surge `permission_live.active`;
- `last_scan.cluster_confirmed`;
- `last_scan.qualified_symbols`;
- `last_scan.promoted_symbols`;
- `/paper/no-entry-diagnostic?force=1`.

Determine whether any promoted candidate was accepted or blocked by normal core timing, quality, cooldown, position, risk, or execution controls. Any accepted opening-surge entry must remain one reduced-size position.

## Previous Reliability Work Still in Force

- `run_report_guard.py` v2 — `d1915e5a79282d0f6ccd541c6024421cf8ad86cd`
- concurrent manual cycles return `cycle_busy` rather than waiting for Gunicorn timeout;
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
- repeated Railway entry-stack validation;
- July 30 missed-opening evidence and root cause documented;
- bounded opening-surge strategy implemented;
- opening-surge v2 chain-aware ownership deployed and initially validated;
- duplicate breakout wrapper defect identified from Railway callable evidence;
- breakout scanner ownership guard implemented, source-tested, activated in Gunicorn, and documented here.

Pending:

- Railway serves the breakout scanner ownership guard;
- one breakout guard and one opening-surge guard remain stable after a recurring watchdog interval;
- opening surge remains above breakout;
- entry ownership and compact self-check remain passing;
- next eligible opening records real cluster, promotion, and candidate-to-entry evidence.

## Exact Next Action

After Railway deploys commits `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43` and `115e921ecdfeb50fde4b4b1125787e9bb190352d`, run `/paper/breakout-scanner-ownership-status`. Then run `/paper/opening-surge-participation-status`, `/paper/bear-recovery-stack-status`, and `/paper/self-check`. Repeat the breakout and opening-surge ownership routes after at least 60 seconds to prove the scanner stack remains singular and correctly ordered.