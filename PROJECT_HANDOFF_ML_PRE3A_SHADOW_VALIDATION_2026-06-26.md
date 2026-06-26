ML Pre-3A Shadow Validation — June 26, 2026

Purpose

Add the safe ML update recommended before Phase 3A: better shadow validation, scorecards, MAE/MFE coverage checks, prediction review, and chronological walk-forward diagnostics without giving ML trade authority.

Files changed

1. ml_pre3a_shadow_validation.py

* Commit: 89b794873b15388adf905adc415ceeabfd52b89d
* File SHA: 3adb2692e537f6bada8a2de3dfde4681fdd295e5
* Version: ml-pre3a-shadow-validation-2026-06-26-v1

2. usercustomize.py

* Commit: 7c1f3a1615c739f2d86797d03432d5f93b5332ad
* File SHA: 3af711ddd050d33a00b5cbb8f8fae5029444c869
* Version: usercustomize-core-entry-ml-pre3a-2026-06-26-v14

Routes

* /paper/ml-pre3a-shadow-status
* /paper/ml-shadow-scorecards
* /paper/ml-shadow-validation

Behavior

* Advisory only.
* Reads current state and ML dataset rows.
* Builds scorecards by symbol, bucket, sector, regime, and decision.
* Checks MAE/MFE/path telemetry coverage from existing recorded fields only.
* Runs chronological train/forward-test validation from realized exits.
* Compares current candidates with stored ML2 shadow predictions.
* Reports Phase 3A gates clearly.
* Does not place trades.
* Does not change sizing.
* Does not override risk controls.
* Does not patch runtime trading functions.
* Does not grant live ML authority.

Expected validation after Railway redeploy

Use:

https://trading-bot-clean.up.railway.app/paper/ml-pre3a-shadow-status

Expected fields:

* version: ml-pre3a-shadow-validation-2026-06-26-v1
* ml_authority: shadow_only
* live_trade_decider: false
* phase3a_live_authority_allowed: false
* policy.does_not_patch_runtime_functions: true
* scorecards
* mae_mfe
* walk_forward
* prediction_review

Then use:

https://trading-bot-clean.up.railway.app/paper/runner-freshness

Expected:

* last_error: null
* stale_during_market: false

Notes

This update is safe to run before Phase 3A because it is read-only/advisory. Phase 3A authority remains blocked until execution rows, labeled outcomes, MAE/MFE coverage, regime coverage, and walk-forward validation gates pass.
