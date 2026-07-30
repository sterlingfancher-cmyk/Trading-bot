# Automated Trading Project Handoff — Updated July 30, 2026

## Engineering Constitution

1. Reliability before performance.
2. Evidence before modification.
3. Deterministic behavior before adaptive behavior.
4. Diagnostics before optimization.
5. Backtests do not replace live paper validation.
6. New capability must improve measurable performance without weakening hard risk controls.
7. Machine learning remains advisory until sufficient execution history, observed outcomes, out-of-sample evidence, and regime stability justify greater influence.
8. Significant changes must be traceable, reversible, and validated before becoming the new baseline.
9. No filter, threshold, risk control, or extension guard may be relaxed merely to force deployment.
10. Runtime callable ownership must be deterministic; competing wrappers and watchdog races are defects.

## Standing Rule

Every code or configuration update must update this handoff in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Always Resume Here

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Default branch: `main`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Operating mode: paper only.
- Live-trading authority: none.
- ML execution authority: none; advisory only.
- July 29 performance-risk, regime-integrity, bear-recovery, and callable-ownership work is source-complete and passed Railway ownership validation.
- July 30 opening-surge participation valve is source-complete; Railway runtime validation is pending deployment.
- Current public entry stack remains:
  1. bear soft-pause short recovery — outer entry-risk owner;
  2. Entry Pipeline X-Ray — one diagnostic wrapper;
  3. deterministic breakout/composition callable;
  4. direct core entry pipeline.
- Current wrapper counts: exactly one bear wrapper and one X-Ray wrapper.
- The opening-surge module wraps `risk_parameters` and `scan_signals`; it does not wrap or replace `try_entries_and_rotations`, so it must not disturb the validated entry stack.
- First current endpoint after Railway deploy:
  - `/paper/opening-surge-participation-status`
- Then verify:
  - `/paper/entry-pipeline-xray-bear-ownership-status`
  - `/paper/bear-recovery-stack-status`
  - `/paper/no-entry-diagnostic?force=1`
  - `/paper/self-check`
- Do not lower the `0.014` bear-recovery short floor, weaken hard loss limits, enable live authority, or broadly enable defensive-regime longs.

## Executive Status Dashboard

| Item | Current status |
|---|---|
| Project phase | Paper performance calibration, regime integrity, controlled bear recovery, opening-surge participation, and runtime validation |
| July 29 repaired scope | Complete and Railway-validated |
| July 30 opening-surge source | Complete; Railway validation pending |
| Account snapshot | Cash/equity approximately `$10,734.80`; no open exposure in supplied morning test |
| Lifetime exits | 52 |
| Lifetime win rate | 67.31% |
| Lifetime net realized P&L | `+$734.82` |
| Lifetime profit factor | `3.1781` |
| Recent 20 exits | 15 wins / 5 losses; `+$681.29`; PF `3.4278` |
| Global opening warmup | 15 minutes |
| Opening-surge window | 15–45 minutes after the 8:30 CDT open |
| Opening-surge capacity | One reduced-size long per day, empty book only |
| Opening-surge minimum score | `0.045` |
| Opening-surge cluster | At least two independently qualifying leaders |
| Opening-surge NQ requirement | NQ futures at least `+0.80%`, trend up |
| Confirmed-bear opening longs | Never allowed |
| Hard realized/intraday halt | `2.50%` |
| Absolute daily-loss ceiling | `3.00%` |
| Live authority | None |
| ML authority | Advisory only |

## July 29 Performance and Risk Calibration

### Evidence reviewed

The strategy record showed positive expectancy rather than a strategy-quality collapse:

- 52 completed exits, 35 wins and 17 losses;
- lifetime win rate `67.31%`;
- gross profit `$1,072.18`;
- gross loss `-$337.36`;
- net realized profit `+$734.82`;
- lifetime profit factor `3.1781`;
- average win `$30.63`;
- average loss `-$19.84`;
- payoff ratio `1.5437`;
- expectancy `+$14.13` per completed exit;
- recent 20 exits: `75%` win rate, `+$681.29`, PF `3.4278`, expectancy `+$34.06`.

The decision was to preserve the profitable strategy and repair deployment, regime, risk-governance, and callable-ownership defects.

### Active paper risk ladder

- `1.00%` realized-loss soft pause;
- controlled restart only under explicitly eligible conditions;
- `2.50%` hard realized-loss halt;
- `2.50%` hard intraday-drawdown halt;
- `3.00%` absolute daily-loss ceiling;
- controlled-recovery sizing capped at 50%;
- no rotations during controlled recovery.

### Calibration files and commits

- `performance_risk_calibration.py` — `838ec3b23a6e573177e1fd51dd2917e8adda4c25`
- `usercustomize.py` calibration registration — `c5a188597074ae8c83e59f78e6e11903b47a3ec4`
- `fast_self_check_override.py` — `1432b21dbd1d2725c1693da317ca7accd98f7746`
- `performance_risk_activation_guard.py` — `8dba35127a9656826020a5239bf146778628c5da`
- initial activation — `85d06eb45e476ba9d50a27ab1479f694984a5c6c`
- route: `/paper/performance-risk-activation-status`

## Regime Integrity and Underdeployment Repair

### Root causes

1. `risk_off` could disable longs while shorts remained unavailable because bear confirmation failed.
2. The macro engine requested about 30 calendar days while requiring at least 30 daily bars, causing unknown SPY/QQQ trends.
3. Market mode was assigned before all futures, breadth, and defensive overlays were applied.
4. A long-oriented soft-pause block globally prevented a valid confirmed-bear short sleeve.

### Implemented behavior

`regime_integrity_underdeployment.py` and its cache guard now:

- request sufficient macro history;
- expose macro bar counts;
- rebuild SPY and QQQ trends from adequate data;
- expose five-day SPY, QQQ, VIX, and Treasury-rate changes;
- expose an auditable risk-score ledger;
- recompute final mode, regime, and permission after all confirmation layers;
- require all bear-confirmation tests before enabling shorts;
- preserve market-data cache behavior.

### Railway evidence

The repaired July 29 runtime showed:

- SPY trend down;
- QQQ trend down;
- SPY five-day return `-1.97%`;
- QQQ five-day return `-5.77%`;
- VIX five-day change `+17.83%`;
- all five bear-confirmation tests true;
- risk score `0`;
- mode `risk_off`;
- regime `bear`;
- permission `short_bias`;
- longs disabled and shorts enabled;
- prior neither-side permission dead zone eliminated.

### Commits and routes

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

The short uses a maximum `0.50` allocation factor. Longs remain blocked and rotations remain disabled.

- recovery policy — `599dcc98355eb9ba4c46920576d1c4eb26f4ecfe`
- worker activation — `4e4b27463d28652aae294ebd49c8976bfaa7b93d`
- route: `/paper/bear-short-recovery-status`

## Entry-Pipeline Ownership Repair

### Required stack

1. bear soft-pause short recovery;
2. one Entry Pipeline X-Ray;
3. breakout/composition guard;
4. direct core entry pipeline.

Observed invalid stacks included composition displacing bear recovery, duplicate bear wrappers, and duplicate X-Ray wrappers.

`bear_recovery_stack_contract.py` v2 normalizes to one bear and one X-Ray. `entry_pipeline_xray_bear_ownership_guard.py` prevents X-Ray from wrapping above an already valid bear-owned stack.

### Commits

- initial contract — `61287a0b8dd6f89a073a17e11904a72723901340`
- initial registration — `0bc442df367e482fa3526a92d096db04f6be7bbb`
- duplicate edge repair — `38a3c935c844716f11f12ab426573e3e83707cf7`
- v2 contract — `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring owner order — `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- X-Ray producer guard — `6589dd791c85575214af103df4414e678441daff`
- final registration — `8f071f172aec72273288abf92c50fd4697db1856`
- pre-validation handoff — `d677e1b7528c4869193730771d26cbf482918d9b`
- final July 29 handoff validation — `e1e70544fbdd4e368cacea068d268d3673f1ff10`

### Railway validation

At 12:36:08 and again at 12:37:41 CDT on July 29:

- ownership routes passed;
- `owned: true`;
- `entry_guard_active: true`;
- one bear wrapper;
- one X-Ray wrapper;
- deterministic composition metadata present;
- direct-core metadata present;
- no drift or oscillation after a recurring repair interval.

The July 29 callable-ownership defect is closed.

## July 30 Morning Opening-Surge Investigation

### Supplied runtime evidence

At 09:08:52 CDT:

- market had been open 38.9 minutes;
- global 15-minute warmup was inactive;
- `new_entries_allowed_last_cycle: true`;
- no hard risk halt, profit guard, self-defense, loss, or drawdown block was active;
- scanner found 12 signals: six long and six short;
- mode was `crash_warning`, regime `bear`, risk score `14`;
- futures were `bullish_but_extended` with NQ `+1.439%`, NQ trend up, and `gap_chase_protection`;
- weak breadth remained active;
- both `allow_longs` and `allow_shorts` were false;
- the primary no-entry driver was `longs_disabled_by_regime`.

High-score rejected long examples included:

- AMD `0.066916`;
- ALAB `0.051672`;
- MU `0.050216`;
- ACLS `0.048229`;
- MRVL `0.039829`.

They were stored as `extended_above_5m_ma20` by 09:05. This shows the bot detected the leaders but reached the ordinary no-chase layer only after the best opening participation window had passed.

### Supplied chart evidence

The user supplied approximately 09:09–09:11 screenshots showing broad compute, semiconductor, AI infrastructure, crypto-compute, and power-infrastructure strength:

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

Not every large prior-close gain was a valid opening breakout. LRCX and PWR were below their opening prices in the supplied screenshots, demonstrating gap-and-fade risk. The new valve therefore requires positive post-open follow-through rather than using the prior-close percentage alone.

### Root cause

This was not a one-hour no-trade rule. The source default global warmup is 15 minutes, and the runtime confirmed it had expired. The missed opportunity was a regime/permission mismatch:

- defensive macro history produced `crash_warning`;
- current NQ/opening tape and individual leaders showed a strong bullish dislocation;
- ordinary longs were globally disabled;
- the existing relative-strength exception also explicitly refused `crash_warning` and `risk_off`;
- by the time the normal scanner accumulated enough bars, leaders were labeled extended.

## Opening-Surge Participation Valve — July 30

### File and version

- file: `opening_surge_participation.py`
- version: `opening-surge-participation-2026-07-30-v1`
- source commit: `2351b9b70e22df414aba248abc5e60b03d477431`
- Gunicorn activation: `3ec95ac24b1eed95367a3fe74813895388cb1a27`
- route: `/paper/opening-surge-participation-status`

### Design

This is a bounded defensive-dislocation exception, not a general risk-off long permission.

It wraps:

- `risk_parameters` to expose one temporary long slot only while all opening-surge conditions are active;
- `scan_signals` to replace ordinary longs with only qualified opening-surge leaders during that temporary permission.

It does not wrap or replace `try_entries_and_rotations`, place orders directly, bypass the core entry pipeline, or alter the validated bear/X-Ray ownership stack.

### Permission requirements

All must be true:

- paper context;
- regular market open;
- normal opening warmup complete;
- 15–45 minutes after open;
- mode `crash_warning` or `risk_off`;
- `bear_confirmed` is false;
- NQ futures at least `+0.80%`;
- NQ intraday trend up;
- bullish, bullish-but-extended, or gap-chase futures context;
- no hard halt;
- no profit guard;
- no self-defense or feedback hard halt;
- no global feedback entry block;
- daily loss and intraday drawdown each below `0.50%`;
- empty book;
- opening-surge daily allowance unused.

### Candidate requirements

A candidate must have:

- score at least `0.045`;
- total move versus prior close between `+8%` and `+20%`;
- post-open follow-through between `+4%` and `+8%`;
- break above the first three five-minute bars' opening range;
- price holding within 1.5% of the session high;
- fast momentum hold;
- relative volume at least `1.25`, unless the post-open move itself is at least 8%;
- an approved compute, semiconductor, AI infrastructure, crypto-compute, power, momentum, cloud/software, space, or dynamic-discovery bucket.

At least two names must qualify in the same scan. The scanner may promote at most three candidates, while the risk permission permits at most one opening-surge entry for the day.

### Sizing and limits

- maximum effective long allocation percentage supplied to the normal pipeline: `5%` of equity before downstream bucket/signal factors;
- empty book only;
- one opening-surge entry per day;
- no confirmed-bear long exception;
- no hard-risk-limit change;
- no live or ML authority;
- all normal core checks remain downstream.

### Universe coverage added

The module ensures these directly observed leaders are represented with sector/bucket hints:

- WDC, CORZ, CRWV, LRCX, NBIS, SNDK, RIOT, AMD, BE, PWR.

This does not mean they are automatically tradable. Each must still pass the opening-surge profile and the core pipeline.

### Source validation completed

- module compiled successfully;
- stub simulation confirmed `crash_warning` plus NQ `+1.4%`, up trend, clean risk, no bear confirmation, and a two-name cluster temporarily enables one long slot;
- confirmed-bear state blocks the exception;
- a previously used daily allowance blocks further opening-surge entries;
- promoted signals retain reduced-size tags and enter the existing core pipeline.

Railway runtime validation remains pending.

## Safety and Authority Boundary

Current changes preserve:

- paper-only operation;
- no live broker authority;
- no ML execution authority;
- no direct order placement by the new module;
- no change to 2.50% hard realized-loss or intraday-drawdown halts;
- no change to the 3.00% absolute daily-loss ceiling;
- no confirmed-bear long exception;
- no broad defensive-regime long permission;
- no relaxation of the ordinary extension guard;
- no change to the bear soft-pause short policy;
- no change to the validated entry ownership stack.

The July 30 module intentionally changes scanner supply, defensive-dislocation strategy permission, and reduced opening sizing within its narrow window. Those changes are explicit and paper-only.

## Validation Order After Railway Deploy

### 1. Opening-surge module installation

`/paper/opening-surge-participation-status`

Expected regardless of time of day:

- version `opening-surge-participation-2026-07-30-v1`;
- `overall: pass`;
- `risk_guard_active: true`;
- `scan_guard_active: true`.

Outside the 15–45 minute window, `permission_live.active: false` is normal. The reasons should identify the time window or current market context rather than an installation failure.

During an eligible opening dislocation, expect:

- `permission_live.active: true`;
- `bear_confirmed: false`;
- bullish NQ futures confirmed;
- daily allowance remaining;
- `last_scan.cluster_confirmed: true` when at least two candidates pass;
- populated `qualified_symbols` and `promoted_symbols`.

### 2. Entry-stack ownership regression check

- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/bear-recovery-stack-status`

Expected:

- both pass;
- `owned: true`;
- `entry_guard_active: true`;
- exactly one bear wrapper and one X-Ray wrapper.

### 3. No-entry or accepted-entry attribution

- `/paper/no-entry-diagnostic?force=1`

Confirm whether an opening-surge candidate was:

- promoted and accepted;
- blocked by core timing/quality/risk controls;
- excluded because the cluster, score, follow-through, volume, or range structure was not confirmed;
- unavailable because the window or defensive-dislocation permission was inactive.

### 4. Compact system check

- `/paper/self-check`

Use `/paper/full-self-check` only after a failed compact check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Previous Reliability Work Still in Force

- `run_report_guard.py` version `run-report-guard-2026-07-24-v2` — `d1915e5a79282d0f6ccd541c6024421cf8ad86cd`
- concurrent manual runs must return `cycle_busy` rather than waiting for Gunicorn timeout.
- PR #6 merge — `9998c597ef91b5d6edce47cdf481efcb6ac4cc90`
- state provenance v2 — `9ce6ddc4e03c38a7c9c4f5e103c2fbbad7f0892b`
- missing-reason trace — `f42f4c985a7f1a7695c6cafdc46584ab379a63d8`
- missing-reason registration — `e0cbdd54775e2e6f17ced686b4e31e3f619d159f`

## Machine Learning Roadmap

ML remains advisory. Before stronger authority:

- decision, blocker, execution, position, and outcome records must remain joinable;
- feature and regime provenance must be stable;
- labels must be complete and leakage-free;
- persistence must be trustworthy;
- at least 150 execution rows and 100 observed outcomes are required but not sufficient;
- offline train/validation/test and walk-forward evidence must show incremental value;
- shadow inference must run without decision authority.

Any ML influence over ranking, sizing, entry permission, or capital requires explicit approval.

## Definition of Done — Opening-Surge Repair

Source complete:

- July 30 evidence and root cause documented;
- bounded permission and scanner valve implemented;
- module compiles;
- simulated permission, cluster, bear veto, and daily-limit tests pass;
- Gunicorn startup registration committed;
- handoff updated.

Railway completion criteria:

- Railway serves the new version;
- installation route passes;
- risk and scan wrappers remain active after a recurring watchdog interval;
- existing bear/X-Ray ownership routes remain passing;
- a future eligible opening cycle records qualified and promoted symbols without broadly enabling ordinary defensive-regime longs;
- any accepted entry is at most one reduced-size position and still clears core controls;
- no newly timestamped critical self-check error appears.

## Next Action

After Railway deploys commits `2351b9b70e22df414aba248abc5e60b03d477431` and `3ec95ac24b1eed95367a3fe74813895388cb1a27`, run `/paper/opening-surge-participation-status`. Then confirm the existing entry-stack ownership routes still pass. On the next market open, evaluate `permission_live`, `last_scan`, and `/paper/no-entry-diagnostic?force=1` between 08:45 and 09:15 CDT. Do not judge the module solely from a later out-of-window status response.