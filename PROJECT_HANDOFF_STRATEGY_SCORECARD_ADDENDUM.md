Strategy Scorecard Addendum — June 16, 2026

Purpose

Upgrade strategy scorecards from strategy_id only into a multi-dimensional advisory analytics layer covering:

* strategy_id
* setup_family
* bucket / theme

This supports the current goal of learning which setup families and baskets actually work before giving any strategy more authority.

File changed

strategy_scorecard.py

Current version

strategy-scorecard-2026-06-16-v2-setup-bucket

Commit

* eec1b879929445ee89cc1bd56c473aa28fd44a83
  * Upgraded strategy_scorecard.py by setup family and bucket.
  * strategy_scorecard.py SHA after update: 626bd3ab672c160257e5c37ba514fc97e3a4636f.

Routes

* /paper/strategy-scorecard-status
* /paper/strategy-id-scorecards
* /paper/strategy-promotion-candidates
* /paper/setup-family-scorecards
* /paper/bucket-scorecards

Watched setup families

* market_surge_stock_leader
* hybrid_market_surge_stock_leader
* market_surge_etf_anchor
* hybrid_market_surge_etf_anchor
* post_harvest_redeployment
* controlled_post_harvest_redeployment_ladder
* pullback_reclaim
* relative_strength_leader
* space_stocks
* bitcoin_ai_compute
* small_cap_momentum

Watched buckets

* space_stocks
* bitcoin_ai_compute
* small_cap_momentum
* semi_leaders
* mega_cap_ai
* cloud_cyber_software
* data_center_infra
* precious_metals
* energy_leaders
* benchmark_etf

Metrics tracked

* execution rows
* entry rows
* exit rows
* wins
* losses
* flats
* win rate
* loss rate
* gross profit
* gross loss
* profit factor
* net PnL
* expectancy per exit
* average win
* average loss
* best trade
* worst trade
* recent W/L/F results
* top symbols
* open position count
* open market value
* open unrealized PnL
* active symbols
* sample confidence
* advisory rotation action

Advisory actions

* collect_more_data
* maintain_observation
* promote_candidate_advisory
* demote_candidate_advisory

Guardrails

* Advisory only.
* Paper-only analytics.
* No live trade authority.
* ML remains shadow-only.
* Does not place trades.
* Does not bypass risk controls.
* Promotion/demotion labels are advisory only until Phase 3A sample-size and walk-forward gates pass.

Startup wiring

strategy_scorecard.py was already wired in wsgi.py. The existing wsgi tuple loads:

("strategy_scorecard", (("apply", (core,)), ("register_routes", (app, core)))),

No additional startup wiring was required for the module itself.

Routine post-deploy check

Use only:

https://trading-bot-clean.up.railway.app/paper/self-check

Optional diagnostics only when intentionally reviewing scorecards:

https://trading-bot-clean.up.railway.app/paper/strategy-scorecard-status

https://trading-bot-clean.up.railway.app/paper/setup-family-scorecards

https://trading-bot-clean.up.railway.app/paper/bucket-scorecards
