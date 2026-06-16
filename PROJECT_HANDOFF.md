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

Important note from the June 16 self-check:

* The old bad blocker losses_today_not_clean did not appear as the active reason.
* The remaining blocker before the last follow-up patch was cash_pct_below_post_harvest_threshold.
* That cash gate has now been converted to a graduated opportunity throttle by post_harvest_opportunity_governor.py.

Recent Critical Fixes

Post-harvest redeployment opportunity governor

Problem observed:

* The post-harvest controller was too blunt after profit-taking or one small controlled loss.
* In post_harvest_redeployment_controller.py, MAX_LOSSES_TODAY defaulted to 0.
* _risk_ok blocked when losses_today > MAX_LOSSES_TODAY.
* This created the bad behavior seen in the midday test:
  * post_harvest_reason: losses_today_not_clean
* The fallback module had the same pattern and could independently block after one small loss.

Goal:

* One small loss today should not block redeployment by itself.
* Profit-taking should not block redeployment by itself.
* Slightly-below-old-threshold cash after an exit should not block redeployment by itself when risk is clean and quality is high.
* Losses, profit-taking, and cash percentage should create a graduated throttle, not a full stop.
* Hard safety blocks must remain intact.

Files involved:

* post_harvest_opportunity_governor.py
* post_harvest_redeployment_controller.py
* post_harvest_entry_fallback.py
* usercustomize.py
* sitecustomize.py
* wsgi.py

New/updated module:

post_harvest_opportunity_governor.py

Current version:

post-harvest-opportunity-governor-2026-06-16-v3-cash-gate-throttle

Route:

* /paper/post-harvest-opportunity-governor-status

Startup wiring:

* usercustomize.py now registers post_harvest_opportunity_governor in _register_auxiliary_routes.
* usercustomize.py now includes /paper/post-harvest-opportunity-governor-status in optional self-check endpoint metadata.
* usercustomize.py watchdog now re-registers post_harvest_opportunity_governor beside:
  * post_harvest_redeployment_controller
  * post_harvest_entry_fallback
* sitecustomize.py already imports/registers usercustomize, so this is the preferred clean wiring path.
* wsgi.py did not need a direct change for this update.

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

* Under 0.50% drawdown:
  * Mode: normal_opportunity.
  * Size factor: 1.00.
  * Cash floor: 50%.
  * Quality: normal post-harvest quality.
* 0.50% to 1.00% drawdown:
  * Mode: cautious_opportunity.
  * Size factor: 0.75.
  * Cash floor: 55%.
  * Quality: higher quality only.
* 1.00% to 2.00% drawdown:
  * Mode: defensive_opportunity.
  * Size factor: 0.50.
  * Cash floor: 60%.
  * Quality: exceptional or relative-strength only.
* 2.00% to 2.75% drawdown:
  * Mode: near_limit_opportunity.
  * Size factor: 0.35.
  * Cash floor: 65%.
  * Quality: best-only small starters.
* 2.75%+ drawdown:
  * Mode: hard_block.
  * No new post-harvest redeployment.

Hard blocks still preserved:

* Risk halt active.
* Self-defense active.
* Hard drawdown limit reached.
* Bear/risk-off market block.
* Normal entry quality failure.
* Max positions full.
* Missing price/data.
* Cooldown.
* No forced trades.
* No bypass of risk halts.
* No bypass of self-defense.
* No live trading.
* No ML authority promotion.

Important interpretation of the latest self-check:

* losses_today was 1.
* self_defense_active was false.
* intraday_drawdown_pct was 0.51.
* cash percentage was 57.64%.
* Before the final cash-gate patch, the system stood down because cash was below the old fixed 60% post-harvest threshold.
* With the final governor patch, 0.51% drawdown maps to cautious_opportunity mode.
* In cautious_opportunity mode, the active cash floor is 55%, not the old fixed 60%.
* Therefore, cash at 57.64% should not be the sole hard blocker after redeploy.
* New entries are still allowed only if risk is clean, the market is not bear/risk-off, there is room under max positions, cooldown/data checks pass, and candidates clear the higher cautious-quality requirement.

Commits for this update sequence:

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

Post-deploy routine test rule:

* Use only: https://trading-bot-clean.up.railway.app/paper/self-check
* Do not run mutating endpoints.
* Do not run repair endpoints unless intentionally repairing malformed state.
* Do not run execution endpoints unless intentionally executing during regular market hours and the user explicitly asks.

What to look for in the next self-check:

* overall: pass.
* status: ok.
* self_defense_active: false.
* ML still shadow-only.
* live trade authority still none.
* No post-harvest hard block solely due to losses_today_not_clean.
* No post-harvest hard block solely due to profit-taking.
* No post-harvest hard block solely because cash is slightly below the old 60% threshold when the active throttle band allows a lower cash floor.
* If no entries occur, acceptable reasons include:
  * no candidate qualified.
  * normal entry quality failure.
  * max positions full.
  * market risk-off/bear block.
  * missing data or price.
  * cooldown.
  * hard drawdown limit.
  * risk halt.
  * self-defense active.

SPY malformed paper position repair

A prior market surge queue executor entry deducted cash for SPY but stored the position in a malformed format. SPY showed entry_price and qty, but the normal status route expected legacy fields entry and shares.

This caused equity and risk controls to appear wrong.

Fixed with:

* surge_state_repair.py
* Version: surge-state-repair-2026-06-08-v4-clear-stale-halt-flag

Confirmed fixed:

* SPY entry: 739.22.
* SPY shares: 1.182638.
* Equity recalculated correctly.
* Stale 8% drawdown flags cleared.
* Stale halt flags cleared.
* Self-check returned pass afterward.

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
* ETF fallback basket if no stock leader qualifies:
  * QQQ up to 20%.
  * SPY up to 10%.
  * SMH up to 5%.

Tier 3 surge:

* Max total deployment: 55%.
* Stock leader sleeve: 70% of surge deployment target.
* ETF anchor sleeve: 30% of surge deployment target.
* Max stock leaders: 5.
* ETF fallback basket if no stock leader qualifies:
  * QQQ up to 20%.
  * SPY up to 15%.
  * SMH up to 10%.
  * IWM up to 7.5%.

Stock leader selection:

* Pulls potential leaders from scanner/surge state containers such as:
  * long_signals
  * short_signals
  * scanner_signals
  * ranked_signals
  * candidate_signals
  * top_candidates
  * top_scanner_candidates
  * top_blocked_candidates
  * blocked_candidates
  * blocked_entries
  * top_blocked_symbols
  * candidate_symbols
  * leader_symbols
  * surge_leaders
  * relative_strength_leaders
  * breakout_candidates
* Dedupe by symbol.
* Exclude already-open symbols.
* Exclude ETFs from the individual stock leader sleeve.
* Require usable price data.
* Require price of at least 3.00.
* Require score >= 0.038, or score >= 0.032 with relative-strength, breakout, or volume confirmation.
* Tier 3 also allows score >= 0.032 with relative-strength or breakout confirmation.
* Rank leaders by score, then relative strength, breakout, and volume confirmation.

ETF role:

* ETFs are no longer the entire market surge strategy.
* If stock leaders qualify, ETFs are reduced to the anchor sleeve.
* If no stock leader qualifies, ETFs can use the original surge fallback basket.
* ETF-only mode should now be interpreted as fallback behavior, not the intended upside engine.

Risk cap:

* Max account risk per entry: 0.80%.
* Default stop loss: 3.5%.
* Default trailing stop: 2.25%.
* Profit activation: 1.5%.
* Profit lock: 0.75%.

Latest market surge update commit:

* 83206d3d2262a26a782ad0a16ad132fb3b69fdac
  * Converted market_surge_deployment_mode.py from ETF-only to hybrid ETF anchor plus stock leaders.
  * market_surge_deployment_mode.py SHA after this commit: 7ee874474a7ee605c7fdedf2a158a088a3bd2fa4.

Important wsgi.py Wiring Correction

The repo’s wsgi.py does not use a plain string list for modules. It uses tuple wiring.

Do not add:

"market_surge_deployment_mode",

Correct line inside the module tuple list:

("market_surge_deployment_mode", (("apply", (core,)), ("register_routes", (app, core)))),

Place it directly after:

("market_surge_queue_executor", (("apply", (core,)), ("register_routes", (app, core)))),

The section should look like:

("market_surge_aggression", (("apply", (core,)), ("register_routes", (app, core)))),
("market_surge_queue_executor", (("apply", (core,)), ("register_routes", (app, core)))),
("market_surge_deployment_mode", (("apply", (core,)), ("register_routes", (app, core)))),
("surge_state_repair", (("apply", (core,)), ("register_routes", (app, core)))),

Post-Deploy Testing Guidance

Routine test after normal pushes:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostic routes only if intentionally debugging:

https://trading-bot-clean.up.railway.app/paper/post-harvest-opportunity-governor-status

https://trading-bot-clean.up.railway.app/paper/market-surge-deployment-status

Heavy routes and execution routes are not part of routine post-push testing.

Current Trading Development Priorities

1. Confirm the next self-check after Railway redeploy shows post-harvest opportunity governor active.
2. Verify losses_today_not_clean is no longer a hard redeployment blocker.
3. Verify cash_pct_below_post_harvest_threshold is no longer a hard blocker when the active throttle band allows the current cash percentage.
4. Confirm market_surge_deployment_mode reports mode: hybrid_etf_anchor_plus_stock_leaders.
5. On the next broad market surge day, confirm the surge plan prioritizes scanner-qualified individual stock leaders before ETF anchors.
6. Confirm ETFs appear as anchor/fallback entries, not as the only surge engine when stock leaders qualify.
7. Keep collecting execution rows toward 150.
8. Keep ML shadow-only until Phase 3A readiness improves.
9. Maintain paper-only guardrails.
10. Do not enable live trading.
11. Do not bypass self-defense or risk halts.
12. Continue favoring full replacement files or direct GitHub connector updates with clear commit/file SHA confirmation.

User Preference / Workflow Notes

* User prefers full replacement files over partial patches.
* Downloadable files or direct GitHub updates are preferred.
* No smart quotes in code.
* No incomplete code snippets.
* Plain code blocks or downloadable .txt files are preferred when not using the GitHub connector.
* After a push, give commit SHA and changed file SHAs.
* Routine testing should stay lightweight and mobile-safe.
