# Automated Trading Project Handoff — Updated July 29, 2026

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
- July 29 performance/risk, regime-integrity, bear-recovery, and entry-ownership repair sequence: **source complete and Railway ownership validation passed**.
- Current public entry stack:
  1. bear soft-pause short recovery — outer risk owner;
  2. Entry Pipeline X-Ray — one diagnostic wrapper;
  3. deterministic breakout/composition callable;
  4. direct core entry pipeline.
- Current wrapper counts: exactly one bear wrapper and one X-Ray wrapper.
- Current next action: continue normal paper cycles and inspect the bear-recovery decision for the stored `XOM` short candidate; do not force an entry or loosen the `0.014` score requirement.
- Routine endpoints:
  - `/paper/entry-pipeline-xray-bear-ownership-status`
  - `/paper/bear-recovery-stack-status`
  - `/paper/bear-short-recovery-status`
  - `/paper/regime-integrity-status`
  - `/paper/underdeployment-xray?force=1`
  - `/paper/self-check`
- Do not lower the `0.014` bear-recovery short floor, bypass extension protection, add risk-off longs, or weaken hard loss limits to manufacture activity.

## Executive Status Dashboard

| Item | Current status |
|---|---|
| Project phase | Paper performance calibration, regime integrity, controlled bear recovery, and ongoing paper validation |
| July 29 repaired scope | Complete |
| Runtime ownership | Passed on Railway |
| Account snapshot used in this sprint | Cash/equity `$10,734.80`; no open exposure at the initial investigation |
| Lifetime exits | 52 |
| Lifetime win rate | 67.31% |
| Lifetime net realized P&L | `+$734.82` |
| Lifetime profit factor | `3.1781` |
| Recent 20 exits | 15 wins / 5 losses; `+$681.29`; PF `3.4278` |
| Original plateau driver | Underdeployment: permissions, insufficient regime data, global soft-pause blocking, and wrapper ownership prevented valid execution |
| Latest validated regime evidence | Confirmed bear; `risk_off`; `short_bias` |
| Soft-pause state during repair | Realized loss `1.144%`, above the `1.00%` soft pause but below hard limits |
| Hard realized/intraday halt | `2.50%` |
| Absolute daily-loss ceiling | `3.00%` |
| Controlled bear recovery | One qualifying short, 50% allocation factor, no rotations |
| Bear-recovery short floor | Normal short floor `0.012` plus `0.002` safety premium = `0.014` |
| Risk-off long exception | None |
| Latest Railway scanner snapshot | 36 total signals; one stored short symbol, `XOM`; no entry outcome shown by the ownership status |
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
- recent 20 exits: `75%` win rate, `+$681.29`, profit factor `3.4278`, expectancy `+$34.06`.

The decision was to preserve the profitable strategy and repair deployment, regime, risk-governance, and callable-ownership defects.

### Active paper risk ladder

- `1.00%` realized-loss soft pause;
- controlled restart only under explicitly eligible conditions;
- `2.50%` hard realized-loss halt;
- `2.50%` hard intraday-drawdown halt;
- `3.00%` absolute daily-loss ceiling;
- controlled-recovery sizing capped at 50%;
- no rotations during controlled recovery.

Initial controlled restart was long-oriented and limited to `risk_on` or `constructive` markets. It correctly refused risk-off recovery longs but initially blocked the confirmed-bear short sleeve globally.

### Calibration files and commits

- `performance_risk_calibration.py`
  - version: `performance-risk-calibration-2026-07-29-v1`
  - commit: `838ec3b23a6e573177e1fd51dd2917e8adda4c25`
- `usercustomize.py`
  - calibration registration: `c5a188597074ae8c83e59f78e6e11903b47a3ec4`
- `fast_self_check_override.py`
  - calibration visibility: `1432b21dbd1d2725c1693da317ca7accd98f7746`

## Performance-Risk Activation Ownership Repair

### Root cause

`core_entry_pipeline.py` replaced `app.try_entries_and_rotations` after the calibration wrapper was installed. The calibration module also used an early `_PATCHED` return and did not reacquire final ownership.

### Repair

`performance_risk_activation_guard.py` was added to:

- wrap active feedback and entry callables after core initialization;
- recompute live restart state;
- preserve hard halts;
- enforce controlled-restart entry limits;
- enforce the required score;
- prevent rotations;
- remain paper-only and avoid direct order placement.

### Commits and route

- activation guard: `8dba35127a9656826020a5239bf146778628c5da`
- initial Gunicorn activation: `85d06eb45e476ba9d50a27ab1479f694984a5c6c`
- route: `/paper/performance-risk-activation-status`

## Underdeployment Investigation

### Structural permission dead zone

Core `risk_off` parameters disabled longs and enabled shorts only when `bear_confirmed` was true. Before repair, the system could report `risk_off` while failing bear confirmation, leaving neither side tradable.

### Macro-history defect

The regime engine requested about 30 calendar days of daily data while its trend classifier required at least 30 daily bars. This generally yielded only 20–22 market sessions and could leave SPY and QQQ trends `unknown`.

### Final-mode defect

The engine assigned market mode before all futures, breadth, and precious-metals adjustments. The displayed final risk score and active mode could therefore disagree.

### Entry-floor attribution

The long floor was fully reconstructed as `0.042`:

- defensive base: `0.016`;
- two losses today: `+0.008`;
- one stop-loss exit: `+0.012`;
- rising VIX: `+0.002`;
- bearish futures: `+0.004`;
- hidden external/wrapper adjustment: `0.000`.

The controlled-restart long floor was `0.048`, adding the configured `0.006` restart premium. It was not the immediate blocker because longs were correctly disabled in confirmed risk-off conditions.

## Regime Integrity Repair

### Implemented behavior

`regime_integrity_underdeployment.py` and its cache guard now:

- request sufficient macro history;
- expose actual bar counts for every macro symbol;
- rebuild SPY and QQQ trend states from sufficient data;
- calculate five-day SPY, QQQ, VIX, and Treasury-rate changes;
- expose an auditable risk-score component ledger;
- recompute final market mode, regime, and trade permission after confirmation layers;
- require all bear-confirmation tests before enabling shorts;
- avoid adding a risk-off long exception;
- preserve the normal market-data cache.

### Railway evidence

The repaired runtime showed:

- SPY trend: down;
- QQQ trend: down;
- SPY five-day return: `-1.97%`;
- QQQ five-day return: `-5.77%`;
- VIX five-day change: `+17.83%`;
- all five bear-confirmation tests true;
- final risk score: `0`;
- final mode: `risk_off`;
- final regime: `bear`;
- trade permission: `short_bias`;
- longs disabled;
- shorts enabled;
- prior permission dead zone eliminated.

### Commits and routes

- regime repair: `136f74a2078cf1b95b9f2a171a4b07c8e9e8cf56`
- initial startup registration: `a06d0020d640686a4de2894ed383ea3fe85051fd`
- cache preservation: `a713b04d8cf1910ccb71dfe51df396558c20704f`
- final worker activation: `0106e574973668a4dff4bed424653898fed33331`
- routes:
  - `/paper/regime-integrity-status`
  - `/paper/underdeployment-xray?force=1`

## Side-Aware Bear Soft-Pause Recovery

### Policy conflict

After regime repair, the market correctly authorized shorts, but the long-oriented soft-pause governor still applied a global `block_new_entries`. This prevented the valid short sleeve from reaching execution.

### Implemented policy

`bear_soft_pause_short_recovery.py` permits one reduced-size short only when:

- the soft pause is active;
- market mode is `risk_off`;
- trade permission is `short_bias`;
- `bear_confirmed` is true;
- the regular session is open;
- no hard halt is active;
- no late-day block is active;
- no profit guard is active;
- the short score is at least `0.014`;
- the daily recovery-short allowance has not been used.

The recovery position uses a maximum `0.50` allocation factor. Longs remain blocked and rotations remain disabled.

### Commits and route

- recovery policy: `599dcc98355eb9ba4c46920576d1c4eb26f4ecfe`
- worker activation: `4e4b27463d28652aae294ebd49c8976bfaa7b93d`
- route: `/paper/bear-short-recovery-status`

## Entry-Pipeline Ownership and Wrapper-Race Repairs

### Observed race sequence

Multiple recurring layers competed for `app.try_entries_and_rotations`:

1. breakout/composition rebuilt the deterministic core stack;
2. Entry Pipeline X-Ray wrapped the active callable;
3. bear recovery wrapped the active callable;
4. later repairs displaced the bear owner or created duplicate wrappers;
5. a status payload could show a passing `last_enforce` while the current public callable had already drifted.

Observed invalid stacks included:

- breakout composition as the public callable with bear recovery displaced;
- bear recovery -> X-Ray -> bear recovery -> composition;
- X-Ray -> bear recovery -> X-Ray -> composition.

### Deterministic stack contract

The required stack is:

1. bear soft-pause short recovery — outer risk owner;
2. Entry Pipeline X-Ray — one diagnostic wrapper;
3. breakout/composition guard;
4. direct core entry pipeline.

`bear_recovery_stack_contract.py` v2:

- strips all known bear and X-Ray outer wrappers to the composition base;
- rebuilds exactly one X-Ray and one bear owner;
- counts wrappers explicitly;
- requires one bear wrapper and one X-Ray wrapper;
- integrates with legacy composition and ownership guards;
- records scanner evidence separately from ownership evidence.

### X-Ray producer repair

`entry_pipeline_xray._patch()` originally inspected only the public callable. When bear recovery was outermost, it could not see the valid X-Ray beneath it and added another X-Ray above the risk owner.

`entry_pipeline_xray_bear_ownership_guard.py` now:

- makes X-Ray's patcher aware of the outer bear owner;
- refuses to add X-Ray above an active bear gate;
- treats bear recovery -> X-Ray as already patched;
- delegates malformed bear-owned stacks to the deterministic stack contract;
- normalizes existing duplicate wrappers at startup;
- maintains watchdog persistence;
- remains composition-only and paper-only.

### Ownership commits

- initial stack contract: `61287a0b8dd6f89a073a17e11904a72723901340`
- initial stack startup registration: `0bc442df367e482fa3526a92d096db04f6be7bbb`
- duplicate-wrapper edge repair: `38a3c935c844716f11f12ab426573e3e83707cf7`
- stack contract v2: `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring final-owner order: `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- X-Ray bear-ownership producer guard: `6589dd791c85575214af103df4414e678441daff`
- final Gunicorn registration: `8f071f172aec72273288abf92c50fd4697db1856`
- comprehensive pre-validation handoff update: `d677e1b7528c4869193730771d26cbf482918d9b`

### Routes

- `/paper/bear-recovery-stack-status`
- `/paper/entry-pipeline-xray-bear-ownership-status`
- `/paper/entry-pipeline-xray-status`
- `/paper/entry-pipeline-ownership-status`
- `/paper/entry-pipeline-composition-status`

## Final Railway Validation — July 29, 2026

### X-Ray bear-ownership guard

At `2026-07-29 12:36:08 CDT`, Railway returned:

- version `entry-pipeline-xray-bear-ownership-2026-07-29-v1`;
- `overall: pass`;
- `xray_patch_guard_active: true`;
- `valid_xray_below_bear: true`;
- nested stack contract `owned: true`;
- `entry_guard_active: true`;
- exactly one bear wrapper;
- exactly one X-Ray wrapper;
- deterministic composition version populated;
- direct core entry-pipeline version populated;
- no drift detected;
- no runtime error reported.

### Recurring stack stability

A later stack check at `2026-07-29 12:37:41 CDT` remained passing after the recurring repair interval:

- version `bear-recovery-stack-contract-2026-07-29-v2`;
- `overall: pass`;
- `owned: true`;
- `entry_guard_active: true`;
- one bear wrapper;
- one X-Ray wrapper;
- public callable remained bear recovery;
- X-Ray remained immediately below bear recovery;
- composition and direct-core metadata remained intact;
- no wrapper oscillation or duplicate layer reappeared.

This closes the July 29 callable-ownership defect.

## Latest Scanner Evidence

### Earlier zero-candidate sample

Two potential shorts were rejected before entry:

- `UCTT`: score `0.011313`, rejected as `extended_below_5m_ma20`;
- `RIOT`: score `0.009508`, rejected as `extended_below_5m_ma20`.

Both were below the bear-recovery requirement of `0.014`. Remaining in cash was correct.

### Latest supplied cycle

At `2026-07-29 12:36:11 CDT`, the stack diagnostic reported:

- `signals_found: 36`;
- 10 stored long symbols in the preview;
- one stored short symbol: `XOM`;
- no rejected-short preview in that status payload.

This confirms the scanner can supply a short candidate to the owned pipeline. The ownership status does not expose XOM's exact score, entry-quality result, or whether an order was accepted. Do not infer eligibility or execution from symbol presence alone. The next normal-cycle evidence should be read from `/paper/bear-short-recovery-status`, the cycle result, and Entry Pipeline X-Ray.

## Safety and Authority Boundary

The July 29 changes preserve:

- paper-only operation;
- no direct order placement by the new guards;
- no live-trading authority;
- no ML execution authority;
- no risk-off long exception;
- no executable-universe mutation;
- no scanner signal-generation change;
- no lowering of ordinary thresholds;
- no weakening of extension or chase protection;
- at most one 50%-size bear-recovery short during the soft pause;
- `2.50%` hard realized-loss and intraday-drawdown halts;
- `3.00%` absolute daily-loss ceiling;
- no rotations during controlled bear recovery.

## Validation and Operating Order

### Routine ownership check

1. `/paper/entry-pipeline-xray-bear-ownership-status`
2. `/paper/bear-recovery-stack-status`

Expected stable fields:

- ownership `overall: pass`;
- stack `overall: pass`;
- `owned: true`;
- `entry_guard_active: true`;
- `bear_wrapper_count: 1`;
- `xray_wrapper_count: 1`;
- X-Ray patch guard active;
- valid X-Ray immediately below bear recovery.

### Bear-recovery decision check

3. `/paper/bear-short-recovery-status`

During an eligible confirmed bear soft pause, expect:

- entry and feedback guards active;
- recovery active;
- longs false;
- shorts true;
- rotations false;
- required short score `0.014`;
- allocation factor `0.5`;
- one recovery short remaining until used.

A changed market can legitimately make recovery inactive. Use explicit eligibility reasons rather than treating inactivity as an ownership failure.

### Regime and underdeployment checks

4. `/paper/regime-integrity-status`
5. `/paper/underdeployment-xray?force=1` only when a fresh regime/floor snapshot is needed.

### System checks

6. `/paper/self-check`
7. `/paper/full-self-check` only after a failed compact check, missing critical fields, a newly timestamped runtime error, or an unexpected warning.

## Previous Reliability Work Still in Force

The July 24 bounded run-cycle guard remains part of the baseline:

- file: `run_report_guard.py`;
- version: `run-report-guard-2026-07-24-v2`;
- commit: `d1915e5a79282d0f6ccd541c6024421cf8ad86cd`;
- concurrent manual runs must fail promptly with `cycle_busy` rather than waiting until Gunicorn timeout.

Prior merged diagnostics remain relevant:

- PR #6 merge commit: `9998c597ef91b5d6edce47cdf481efcb6ac4cc90`;
- state provenance v2 branch commit: `9ce6ddc4e03c38a7c9c4f5e103c2fbbad7f0892b`;
- missing-reason trace: `f42f4c985a7f1a7695c6cafdc46584ab379a63d8`;
- missing-reason registration: `e0cbdd54775e2e6f17ced686b4e31e3f619d159f`.

## Machine Learning Roadmap

### Current authority

ML remains advisory only. The deterministic strategy, risk engine, and entry pipeline remain authoritative.

### Data-readiness requirements

Before any stronger ML role:

- decision, blocker, execution, position, and outcome records must remain joinable;
- feature and regime provenance must be stable;
- labels must be complete and free from leakage;
- state persistence must be trustworthy;
- at least 150 execution rows and 100 observed outcomes are required, but are not sufficient;
- offline train/validation/test and walk-forward evidence must show incremental value;
- shadow inference must run without decision authority before controlled influence is considered.

Any ML influence over ranking, sizing, entry permission, or capital requires explicit approval.

## Engineering Decision Log — July 29

### Preserve positive expectancy; repair underdeployment

The performance record was profitable. Changes focused on permissions, data sufficiency, risk governance, and runtime ownership rather than replacing the strategy.

### No risk-off recovery longs

Confirmed risk-off conditions continue to block new longs. Recovery activity is limited to a genuinely confirmed bear short sleeve.

### Side-aware soft pause

A global soft-pause block was replaced with side-aware permission only for one reduced-size qualifying short. Hard limits were not relaxed.

### Data sufficiency before bear confirmation

SPY and QQQ trend classification must use enough daily bars. Unknown trends caused by an undersized request window are not valid evidence against bear confirmation.

### Final mode after all overlays

Market mode and trade permission must be recomputed after futures, breadth, and defensive confirmation layers.

### One deterministic public entry stack

The public callable must have one risk owner, one diagnostic X-Ray, one composition layer, and one direct core implementation. Multiple watchdogs may inspect or repair this contract but may not compete for different outer ownership.

### Scanner inactivity is not ownership failure

Zero qualifying candidates is legitimate when no symbol passes trend, score, extension, cooldown, and quality controls. Ownership diagnostics and scanner diagnostics remain distinct.

### Candidate presence is not execution evidence

A symbol appearing in `short_signal_symbols` confirms scanner supply only. Entry eligibility still requires score, extension, quality, risk, sizing, and execution-pipeline approval.

## Files and Commits — July 29 Sprint

- `performance_risk_calibration.py` — `838ec3b23a6e573177e1fd51dd2917e8adda4c25`
- `usercustomize.py` calibration registration — `c5a188597074ae8c83e59f78e6e11903b47a3ec4`
- `fast_self_check_override.py` — `1432b21dbd1d2725c1693da317ca7accd98f7746`
- `performance_risk_activation_guard.py` — `8dba35127a9656826020a5239bf146778628c5da`
- `gunicorn.conf.py` initial activation — `85d06eb45e476ba9d50a27ab1479f694984a5c6c`
- `regime_integrity_underdeployment.py` — `136f74a2078cf1b95b9f2a171a4b07c8e9e8cf56`
- regime startup — `a06d0020d640686a4de2894ed383ea3fe85051fd`
- regime cache preservation — `a713b04d8cf1910ccb71dfe51df396558c20704f`
- final regime worker activation — `0106e574973668a4dff4bed424653898fed33331`
- `bear_soft_pause_short_recovery.py` — `599dcc98355eb9ba4c46920576d1c4eb26f4ecfe`
- bear recovery activation — `4e4b27463d28652aae294ebd49c8976bfaa7b93d`
- `bear_recovery_stack_contract.py` initial — `61287a0b8dd6f89a073a17e11904a72723901340`
- stack startup registration — `0bc442df367e482fa3526a92d096db04f6be7bbb`
- duplicate-stack edge repair — `38a3c935c844716f11f12ab426573e3e83707cf7`
- stack contract v2 — `5f3b023dab814cc32b2f6137043d44fc63293dc5`
- recurring final-owner order — `fddebd39f4fcf2d57f023ce81d916f0936e3c4a3`
- `entry_pipeline_xray_bear_ownership_guard.py` — `6589dd791c85575214af103df4414e678441daff`
- final Gunicorn registration — `8f071f172aec72273288abf92c50fd4697db1856`
- comprehensive pre-validation handoff — `d677e1b7528c4869193730771d26cbf482918d9b`

## Definition of Done — July 29 Repair Sequence

Completed:

- Railway serves `entry-pipeline-xray-bear-ownership-2026-07-29-v1`.
- X-Ray bear-ownership route passes.
- Stack route passes after a recurring repair interval.
- Wrapper counts remain exactly one bear and one X-Ray.
- Entry guard remains active.
- Composition and direct-core metadata remain intact.
- No wrapper oscillation reappears in supplied repeated checks.
- Legitimate zero-candidate cycles remain in cash without weakened controls.
- A later scanner cycle supplies a short candidate through the stable stack.
- The handoff includes the full July 29 sequence and final Railway evidence.

Still part of normal paper validation, not an unresolved ownership defect:

- observe whether `XOM` or a later short reaches the `0.014` floor and passes all ordinary quality/extension controls;
- verify the cycle result and bear-short recovery decision before treating any signal as an accepted entry;
- continue compact self-check monitoring for new runtime errors;
- preserve paper-only authority until broader validation gates are met.

## Next Action

Continue normal paper operation. On the next meaningful cycle, inspect `/paper/bear-short-recovery-status` and Entry Pipeline X-Ray to determine whether the stored short candidate was below score, blocked by quality/extension/risk controls, or accepted. No additional ownership repair is indicated by the final supplied Railway evidence.