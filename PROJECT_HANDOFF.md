Automated Trading Project Handoff — Updated June 16, 2026

Current System Status

Base app URL:

https://trading-bot-clean.up.railway.app

GitHub repo:

sterlingfancher-cmyk/Trading-bot

Current operating mode:

* Paper trading only.
* Live trade authority: none.
* ML authority: shadow-only.
* Routine test link: https://trading-bot-clean.up.railway.app/paper/self-check
* Do not use heavy diagnostic routes unless intentionally debugging.
* Do not run repair routes unless a specific state issue appears.
* Do not run execution routes after hours.
* Do not run mutating Railway endpoints during routine post-push checks.

Latest routine self-check supplied by operator on June 16, 2026 showed:

* Overall: pass.
* Status: ok.
* Warnings: none.
* Checked internal paths: /health and /paper/status.
* Cash: 6296.67.
* Equity: 10924.45.
* Cash percentage: 57.64%.
* Open positions: 3.
* Positions: QQQ, SPY, IWM.
* Realized today: -2.09.
* Realized total: +952.28.
* Unrealized PnL: -27.82.
* Losses today: 1.
* Daily loss pct: 0.465.
* Intraday drawdown pct: 0.51.
* Self-defense active: false.
* Self-defense reason: feedback loop clear.
* Scanner signals found: 53.
* Blocked entries: 15.
* Execution rows: 90 / 150.
* ML remains shadow-only.
* Phase 3A is not ready yet.

Recent Critical Fixes

Post-harvest redeployment opportunity governor

Current version:

post-harvest-opportunity-governor-2026-06-16-v3-cash-gate-throttle

Route:

* /paper/post-harvest-opportunity-governor-status

Purpose:

* Converts the prior blunt losses_today_not_clean behavior into a graduated opportunity throttle.
* Converts the old fixed 60% post-harvest cash threshold into a graduated soft gate.
* Keeps risk halt, self-defense, hard drawdown, market risk-off, max-position, missing-data, cooldown, and quality gates intact.

Runtime patches applied by the governor:

* post_harvest_redeployment_controller._risk_ok
* post_harvest_redeployment_controller._entry_block_safe
* post_harvest_redeployment_controller._profit_harvest_ok
* post_harvest_redeployment_controller._quality_ok
* post_harvest_redeployment_controller._starter_signal
* post_harvest_redeployment_controller.select_redeployment_candidates
* post_harvest_entry_fallback._risk_ok

Policy now active:

* losses_today_policy: throttle_not_hard_block
* profit_taking_policy: frees_capital_if_quality_and_risk_are_clean
* cash_pct_policy: graduated_soft_gate_not_fixed_hard_block
* live_trade_authority remains none.
* ml_authority remains shadow_only.
* authority_changed remains false.

Throttle bands:

* Under 0.50% drawdown: normal_opportunity, 1.00 size factor, 50% cash floor.
* 0.50% to 1.00% drawdown: cautious_opportunity, 0.75 size factor, 55% cash floor.
* 1.00% to 2.00% drawdown: defensive_opportunity, 0.50 size factor, 60% cash floor.
* 2.00% to 2.75% drawdown: near_limit_opportunity, 0.35 size factor, 65% cash floor.
* 2.75%+ drawdown: hard_block.

Important interpretation of the latest self-check:

* losses_today was 1.
* self_defense_active was false.
* intraday_drawdown_pct was 0.51.
* cash percentage was 57.64%.
* Before the final cash-gate patch, the system stood down because cash was below the old fixed 60% post-harvest threshold.
* With the final governor patch, 0.51% drawdown maps to cautious_opportunity mode.
* In cautious_opportunity mode, the active cash floor is 55%, not the old fixed 60%.
* Therefore, cash at 57.64% should not be the sole hard blocker after redeploy.

Commits for the post-harvest update sequence:

* 7a6fb8e018df1368f4c814bb8c9f8b03b9513664
  * Added post_harvest_opportunity_governor.py.
  * File SHA at that point: f4ff29138f46b3bc61417eee8265fa0b0596ec83.
* cb15363495f33aa1b2133e24caf991e67d5d4e20
  * Wired post_harvest_opportunity_governor into usercustomize.py startup.
  * usercustomize.py SHA after this commit: ef653f49c08f35c8c06e0c514ac31002c5c11cf1.
* dee509d0f91cd19606ebea5ccd2a0272a329e6ea
  * Tightened post-harvest opportunity throttle logic.
  * post_harvest_opportunity_governor.py SHA after this commit: 284c9189597664adbe2a43cec1cd664a0ff772a5.
* e662d40a5c6483462c0b1f4ff96a4230450b60da
  * Converted post-harvest cash gate from fixed hard threshold to graduated throttle.
  * post_harvest_opportunity_governor.py SHA after this commit: 2c39c96815ef27f19fd352ba78b339a40ffdb7fe.

Space Stock Basket Overlay

File:

space_stock_basket.py

Current version:

space-stock-basket-2026-06-16-v1

Route:

* /paper/space-stock-basket-status

Purpose:

Adds a focused space / space-infrastructure theme to the active scanner universe without rewriting app.py. This is a metadata and universe overlay only. It does not place trades, change ML authority, bypass risk controls, or force entries.

Why it was added:

* A new space-stock trend is emerging.
* The bot had RKLB already inside SMALL_CAP_MOMENTUM, but it did not have a broader space basket.
* The market surge module was recently changed to prioritize scanner-ranked individual stock leaders.
* Adding a space basket lets qualifying space leaders compete in the normal scanner and hybrid surge stock-leader path.

Symbols added:

Launch / lunar:

* RKLB
* LUNR
* SPCE

Satellite connectivity:

* ASTS
* IRDM
* GSAT
* VSAT
* SATS

Earth observation / space data:

* PL
* BKSY
* SATL
* SPIR

Space infrastructure:

* RDW

Bucket:

* Bucket name: space_stocks.
* Default alloc factor: 0.70.
* Default max exposure pct: 0.30.
* Default max positions: 3.
* Environment overrides:
  * SPACE_STOCKS_ALLOC_FACTOR
  * SPACE_STOCKS_MAX_EXPOSURE_PCT
  * SPACE_STOCKS_MAX_POSITIONS

Sector mapping:

* RKLB, LUNR, SPCE, RDW -> XLI.
* ASTS, PL, BKSY, SATL, SPIR -> XLK.
* IRDM, GSAT, VSAT, SATS -> XLC.

Startup wiring:

* usercustomize.py now registers space_stock_basket.
* usercustomize.py watchdog now re-registers space_stock_basket.
* /paper/space-stock-basket-status is included as optional self-check metadata.

Important behavior:

* These stocks are now available to the scanner universe.
* They still have to pass the normal scanner ranking, risk, quality, price, cooldown, sector/bucket exposure, and max-position rules.
* They can become hybrid market-surge stock leaders only if the scanner/state surfaces them as qualifying leaders.
* No forced trades.
* No live trading.
* No ML authority change.

Commits for the space basket update:

* 5fea442ff21ce828e7cacca0f22b00f2ec3f17f4
  * Added space_stock_basket.py.
  * space_stock_basket.py SHA after creation: d101385c07a27cb215cde4d8d41d85e26a0638f2.
* 73cfd23b4826e69811c32c1244e5d8634400f3b5
  * Wired space_stock_basket into usercustomize.py startup and watchdog.
  * usercustomize.py SHA after this commit: a0bf8c20197c749fc7967b303a34214e80948385.

SPY malformed paper position repair

A prior market surge queue executor entry deducted cash for SPY but stored the position in a malformed format. SPY showed entry_price and qty, but the normal status route expected legacy fields entry and shares.

Fixed with:

* surge_state_repair.py
* Version: surge-state-repair-2026-06-08-v4-clear-stale-halt-flag

Do not run the repair endpoint again unless the state becomes malformed again.

Repair routes:

* /paper/surge-state-repair-status
* /paper/surge-state-repair?confirm=1

Market Surge Deployment Mode

File:

market_surge_deployment_mode.py

Current version:

market-surge-deployment-mode-2026-06-16-v3-hybrid-stock-leaders

Purpose:

Hybrid paper-only market surge deployment mode that prioritizes high-quality individual stock leaders from the scanner while keeping ETFs as a broad-market anchor and fallback.

Routes:

* /paper/market-surge-deployment-status
* /paper/market-surge-deployment-plan
* /paper/market-surge-deployment-execute?confirm=1
* /paper/market-surge-deployment-auto-fire
* /paper/market-surge-deployment-autofire

Core design:

* Paper-only.
* No live trade authority.
* ML remains shadow-only.
* Requires clean risk controls.
* Requires regular market window.
* Requires high cash percentage.
* Requires surge confirmation.
* Uses scanner-ranked individual stock leaders first during broad market surges.
* Uses ETFs as an anchor and fallback, not the ceiling.
* Uses hard stop loss and trailing stop metadata.
* Does not average down.
* Does not execute without confirm=1 on the manual execution route.
* Auto-fire remains paper-only, regular-market-only, risk-clean-only, and limited to one successful fire per local trading day.

Hybrid surge allocation logic:

Tier 2 surge:

* Max total deployment: 35%.
* Stock leader sleeve: 60% of surge deployment target.
* ETF anchor sleeve: 40% of surge deployment target.
* Max stock leaders: 4.
* ETF fallback basket if no stock leader qualifies: QQQ, SPY, SMH.

Tier 3 surge:

* Max total deployment: 55%.
* Stock leader sleeve: 70% of surge deployment target.
* ETF anchor sleeve: 30% of surge deployment target.
* Max stock leaders: 5.
* ETF fallback basket if no stock leader qualifies: QQQ, SPY, SMH, IWM.

Stock leader selection:

* Pulls potential leaders from scanner/surge state containers.
* Dedupe by symbol.
* Exclude already-open symbols.
* Exclude ETFs from the individual stock leader sleeve.
* Require usable price data.
* Require price of at least 3.00.
* Require score >= 0.038, or score >= 0.032 with relative-strength, breakout, or volume confirmation.
* Tier 3 also allows score >= 0.032 with relative-strength or breakout confirmation.
* Rank leaders by score, then relative strength, breakout, and volume confirmation.

Latest market surge update commit:

* 83206d3d2262a26a782ad0a16ad132fb3b69fdac
  * Converted market_surge_deployment_mode.py from ETF-only to hybrid ETF anchor plus stock leaders.
  * market_surge_deployment_mode.py SHA after this commit: 7ee874474a7ee605c7fdedf2a158a088a3bd2fa4.

Important wsgi.py Wiring Correction

The repo’s wsgi.py does not use a plain string list for modules. It uses tuple wiring.

Correct line inside the module tuple list:

("market_surge_deployment_mode", (("apply", (core,)), ("register_routes", (app, core)))),

Place it directly after:

("market_surge_queue_executor", (("apply", (core,)), ("register_routes", (app, core)))),

Post-Deploy Testing Guidance

Routine test after normal pushes:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostic routes only if intentionally debugging:

https://trading-bot-clean.up.railway.app/paper/post-harvest-opportunity-governor-status

https://trading-bot-clean.up.railway.app/paper/market-surge-deployment-status

https://trading-bot-clean.up.railway.app/paper/space-stock-basket-status

Heavy routes and execution routes are not part of routine post-push testing.

Current Trading Development Priorities

1. Confirm the next self-check after Railway redeploy shows post-harvest opportunity governor active.
2. Verify losses_today_not_clean is no longer a hard redeployment blocker.
3. Verify cash_pct_below_post_harvest_threshold is no longer a hard blocker when the active throttle band allows the current cash percentage.
4. Confirm market_surge_deployment_mode reports mode: hybrid_etf_anchor_plus_stock_leaders.
5. Confirm space_stock_basket reports status ok and includes the new space stocks.
6. On the next broad market surge day, confirm the surge plan prioritizes scanner-qualified individual stock leaders before ETF anchors.
7. Confirm ETFs appear as anchor/fallback entries, not as the only surge engine when stock leaders qualify.
8. Watch whether space names appear in scanner audit/top candidates during the current space-stock trend.
9. Keep collecting execution rows toward 150.
10. Keep ML shadow-only until Phase 3A readiness improves.
11. Maintain paper-only guardrails.
12. Do not enable live trading.
13. Do not bypass self-defense or risk halts.
14. Continue favoring full replacement files or direct GitHub connector updates with clear commit/file SHA confirmation.

User Preference / Workflow Notes

* User prefers full replacement files over partial patches.
* Downloadable files or direct GitHub updates are preferred.
* No smart quotes in code.
* No incomplete code snippets.
* Plain code blocks or downloadable .txt files are preferred when not using the GitHub connector.
* After a push, give commit SHA and changed file SHAs.
* Routine testing should stay lightweight and mobile-safe.
