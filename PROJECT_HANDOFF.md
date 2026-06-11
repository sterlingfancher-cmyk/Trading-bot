Automated Trading Project Handoff — Updated June 11, 2026

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

Latest after-hours self-check showed:

* Overall: pass.
* Status: ok.
* Warnings: none.
* Cash: 10960.96.
* Equity: 10960.96.
* Open positions: 0.
* Realized today: 0.00.
* Realized total: +960.98.
* Daily loss pct: 0.0.
* Intraday drawdown pct: 0.0.
* Self-defense active: false.
* Scanner signals found: 39.
* Blocked entries: 0.
* Execution rows: 87 / 150.
* ML remains shadow-only.
* Phase 3A is not ready yet.

Recent Critical Fixes

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

Current Concern

The bot is too passive on broad market surge days.

Recent examples:

* QQQ had a strong surge day.
* S&P 500 had a strong surge day.
* Bot stayed 100% in cash.
* Scanner saw activity, but post-harvest redeployment did not qualify any entries.
* This protected capital, but it missed broad market participation.

The user does not want tiny starter-only allocation during obvious broad market surge conditions. The preferred design is larger surge participation with strict hard stops and trailing stops.

New Module Added / Being Added

New file:

market_surge_deployment_mode.py

Purpose:

Aggressive paper-only market surge deployment mode.

Routes:

* /paper/market-surge-deployment-status
* /paper/market-surge-deployment-plan
* /paper/market-surge-deployment-execute?confirm=1

Core design:

* Paper-only.
* No live trade authority.
* ML remains shadow-only.
* Requires clean risk controls.
* Requires regular market window.
* Requires high cash percentage.
* Requires surge confirmation.
* Uses larger allocations during broad market surge days.
* Uses hard stop loss and trailing stop metadata.
* Does not average down.
* Does not execute without confirm=1.

Planned deployment logic:

Tier 2 surge:

* QQQ up to 20%.
* SPY up to 10%.
* SMH up to 5%.
* Max total deployment: 35%.

Tier 3 surge:

* QQQ up to 20%.
* SPY up to 15%.
* SMH up to 10%.
* IWM up to 7.5%.
* Max total deployment: 55%.

Risk cap:

* Max account risk per entry: 0.80%.
* Default stop loss: 3.5%.
* Default trailing stop: 2.25%.
* Profit activation: 1.5%.
* Profit lock: 0.75%.

Important wsgi.py Wiring Correction

The repo’s wsgi.py does not use a plain string list for modules. It uses tuple wiring.

Do not add:

"market_surge_deployment_mode",

Correct line to add inside the module tuple list:

("market_surge_deployment_mode", (("apply", (core,)), ("register_routes", (app, core)))),

Place it directly after:

("market_surge_queue_executor", (("apply", (core,)), ("register_routes", (app, core)))),

The section should look like:

("market_surge_aggression", (("apply", (core,)), ("register_routes", (app, core)))),
("market_surge_queue_executor", (("apply", (core,)), ("register_routes", (app, core)))),
("market_surge_deployment_mode", (("apply", (core,)), ("register_routes", (app, core)))),
("surge_state_repair", (("apply", (core,)), ("register_routes", (app, core)))),

Suggested commit message:

Wire aggressive market surge deployment mode

Post-Deploy Test

After Railway redeploys, test:

https://trading-bot-clean.up.railway.app/paper/market-surge-deployment-status

Then run normal self-check:

https://trading-bot-clean.up.railway.app/paper/self-check

Do not run the execute endpoint after hours.

Only during regular market hours, and only if status shows deployment_allowed: true and planned_entries is not empty, run:

https://trading-bot-clean.up.railway.app/paper/market-surge-deployment-execute?confirm=1

Then immediately run:

https://trading-bot-clean.up.railway.app/paper/self-check

Current GitHub Workflow Problem

The ChatGPT GitHub connector has recently become unreliable in this thread.

Observed issue:

* Assistant repeatedly tried to access GitHub.
* Connector returned tool-discovery responses instead of moving into actual repo file operations.
* This caused a loop/freeze behavior.
* Retry did not solve it.

Temporary workflow:

* Use downloadable files.
* Use copy/paste-formatted .txt files when GitHub mobile is sensitive to formatting.
* Do not depend on the GitHub connector until the workflow is debugged.

User preference:

* Full replacement files.
* Downloadable file packages.
* Clear instructions.
* No partial patches unless absolutely necessary.
* No smart quotes.
* No incomplete code snippets.
* No writing-style formatting for Python code.
* Plain code blocks or downloadable .txt files are preferred.

Next assistant priority after this module:

Figure out why GitHub tool workflow is failing compared with how it worked a week ago. Do not continue building new trading modules until the GitHub update/push workflow is reliable again, unless the user explicitly asks.

Current Trading Development Priorities

1. Finish wiring and testing market_surge_deployment_mode.py.
2. Confirm route loads:
    * /paper/market-surge-deployment-status
3. Confirm no after-hours execution.
4. Next market surge day, check whether it plans QQQ/SPY/SMH entries correctly.
5. Keep ML shadow-only until Phase 3A readiness improves.
6. Continue collecting execution rows toward 150.
7. Maintain paper-only guardrails.
8. Fix GitHub workflow reliability before major future updates.
