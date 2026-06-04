# Automated Trading Bot Project Handoff

Last updated: 2026-06-04

This file is the project continuity source of truth for future ChatGPT sessions. New chats should read this file, inspect recent GitHub commits, and then continue from the current state without asking the operator to reconstruct prior conversations.

## Repository and deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Main app file: `app.py`
- WSGI startup: `wsgi.py`
- Runtime auxiliary wiring: `usercustomize.py`
- Persistent Railway state: `/data/state.json`
- Routine test link: `https://trading-bot-clean.up.railway.app/paper/self-check`

## Operator preferences

- Preserve the one-test workflow.
- After normal pushes, ask the operator to run only `/paper/self-check`.
- Do not require multiple routine test links unless debugging a specific issue.
- Prefer direct GitHub updates or full-file-safe updates over patch fragments.
- Do not loosen risk controls without explicit approval.
- Do not give ML live trade authority without explicit approval and promotion-gate evidence.
- Keep manual `/paper/run` protected by `RUN_KEY`.
- Keep this handoff updated after meaningful code changes, test results, or strategy-direction changes.

## Handoff maintenance protocol

Every future assistant should treat this file as a living project ledger. After any meaningful update, append or refresh the relevant sections below.

### Required handoff updates after each meaningful push

Update this file when any of the following happens:

1. A code change is pushed.
2. A self-check result changes the known bot state.
3. A new module, route, endpoint, risk rule, or advisory layer is added.
4. A bug is found or resolved.
5. A new next-step priority is chosen.
6. ML readiness gates change.
7. The one-test workflow changes.

### Minimum update fields to preserve

For each future update, record:

- Date/time.
- Commit SHA.
- Files changed.
- Reason for the change.
- Whether trading authority changed.
- Whether ML authority changed.
- Whether risk controls changed.
- Whether the one-test workflow changed.
- Latest `/paper/self-check` result summary.
- Next planned update.

### Permanent rule

If a future chat changes GitHub but does not update this file, the next chat should consider the project handoff stale and should inspect recent commits before making assumptions.

## Recommendation and advisory sources to review

There are several code layers that generate recommendations or advisory feedback. Some of them are intentionally hidden from the mobile-safe one-test output unless they are promoted into `decision_audit_next_actions` or another compact summary. Future chats should review these before deciding the next upgrade.

### Primary routine source

Use this first:

```text
https://trading-bot-clean.up.railway.app/paper/self-check
```

Look for:

- `decision_audit_next_actions`
- `decision_audit_summary`
- `ml_shadow_counts`
- `warnings`
- `operator_summary`
- `truth_summary`

### Recommendation/advisory code modules

Known advisory/recommendation modules include:

- `decision_audit_consolidation.py` — current compact decision audit, post-harvest status, news availability, ML shadow counts, and internal advisory coaches.
- `risk_on_recommendation_cleanup.py` — cleans and deduplicates risk-on recommendation text, including entry-ready/watch candidate wording and market participation accelerator wiring.
- `risk_on_entry_diagnostic.py` — risk-on entry diagnostics and candidate reasoning.
- `entry_decision_visibility.py` — explains entered/blocked/skipped/no-decision behavior.
- `ml_phase2_shadow.py` — ML shadow predictions and recommendation text; never live-authoritative.
- `ml_phase25_readiness.py` — Phase 2.5/Phase 3A readiness gates and recommended actions.
- `mae_mfe_integration.py` — MAE/MFE telemetry readiness and recommended actions.
- `news_sentiment_engine.py` — news/catalyst advisory context and recommended actions.
- `market_extension_guard.py` — market extension/overextension advisories.
- `benchmark_participation.py` — benchmark/risk-on participation diagnostics.
- `adaptive_ml_research.py` — adaptive ML research recommendations.
- `adaptive_portfolio_intelligence.py` — portfolio intelligence/advisory recommendations.
- `strategy_promotion_readiness.py` — strategy promotion gates and readiness feedback.
- `strategy_scorecard.py` — strategy scorecards and performance comparisons.
- `trade_quality_telemetry.py` — trade-quality telemetry and improvement signals.

### Internal advisory coaches

As of 2026-06-04, the repo-native advisory coaches are implemented inside `decision_audit_consolidation.py` and are surfaced through `/paper/self-check` via `decision_audit_next_actions`.

- Trade Quality Coach: reviews execution rows, exits, win/loss quality, profit factor, exit reasons, and symbol-level realized P&L.
- Risk Coach: reviews cash percentage, position count, drawdown, halts, and self-defense state.
- Post-Harvest Coach: reviews post-harvest redeployment posture, underdeployment, qualifying candidates, and whether standing down is appropriate.

These coaches are read-only and advisory-only. They do not trade, resize, change risk rules, change ML authority, or modify post-harvest thresholds.

### Optional deeper diagnostic routes

Only use these when `/paper/self-check` indicates a warning/failure or when choosing the next major upgrade:

```text
/paper/ml2-status
/paper/ml-readiness-status
/paper/decision-audit-status
/paper/no-entry-diagnostic
/paper/risk-on-entry-diagnostic
/paper/strategy-promotion-readiness-status
/paper/strategy-scorecard-status
/paper/mae-mfe-status
/paper/mae-mfe-integration-status
/paper/news-sentiment-status
/paper/catalyst-watchlist
/paper/news-risk-status
/paper/market-extension-status
/paper/risk-reward-status
/paper/adaptive-ml-status
/paper/adaptive-portfolio-status
```

Do not make these part of routine testing. They are for targeted inspection only.

### Why recommendation feedback may disappear from normal view

The project intentionally uses a mobile-safe one-test policy. `/paper/self-check` may internally read state directly and only show `/health` and `/paper/status` as checked paths. That keeps testing fast and stable, but it can hide detailed recommendation text from deeper endpoints. When important recommendations matter, future code should promote a compact version into:

- `decision_audit_next_actions`
- `operator_summary`
- `decision_audit_summary`
- `warnings`, if it is truly actionable

## One-test workflow

Routine post-push test:

```text
https://trading-bot-clean.up.railway.app/paper/self-check
```

Expected characteristics:

- `overall: pass`
- `status: ok`
- `warnings: []`, unless a real diagnostic issue is present
- `single_best_link` points back to `/paper/self-check`
- `routine_test_policy.extra_links_required: false`
- Mobile-safe mode may only internally check `/health` and `/paper/status`, but it also promotes compact summaries from decision audit and ML counts into the payload.

Heavy diagnostic routes are optional and should not be part of routine post-push testing.

## Current high-level bot state

Most recent known self-check state from 2026-06-03 evening:

- Equity: about `$11,023.95`
- Total gain from `$10,000`: about `+10.24%`
- Cash: about `$9,672.49`
- Open positions: `3`
- Positions: `DELL`, `QQQ`, `SNDK`
- Realized today: `$341.36`
- Realized total: `$857.68`
- Unrealized P&L: about `$166.28`
- Losses today: `0`
- Self-defense: inactive in the latest status, final-close lock was previously recognized correctly as protective rather than a warning
- Scanner signals in latest snapshot: about `33`
- Blocked entries in latest snapshot: about `10`

## Active major modules and status

### Core trading engine

- `app.py` owns market regime, scanner, entries, exits, portfolio state, risk controls, `/paper/run`, and `/paper/status`.
- Persistent state is stored under `/data/state.json` on Railway.
- `/paper/run` requires `RUN_KEY`; preferred auth is `X-Run-Key` header.

### Post-harvest redeployment

Files:

- `post_harvest_redeployment_controller.py`
- `post_harvest_entry_fallback.py`

Current purpose:

- Detect when the bot is underdeployed after harvesting profit.
- Redeploy only through 1-2 high-quality starter candidates.
- Keep `max_positions` unchanged.
- Do not bypass halts, stop losses, self-defense, risk controls, or normal entry quality checks.
- Do not force entries.
- Do not rebuy recently harvested symbols unless they requalify strongly.

Recent behavior:

- BTDR was selected as a qualifying post-harvest breakout candidate, but the opportunity faded before a durable entry.
- SNDK later entered, taking the bot from 2 positions to 3 positions.
- Later post-harvest status correctly stood down with `no_candidate_qualified`.

### Decision audit and one-test visibility

File:

- `decision_audit_consolidation.py`

Current version expected after the latest update:

- `decision-audit-consolidation-2026-06-04-v5-advisory-coaches`

Purpose:

- Read-only advisory layer.
- Consolidates scanner/result flow, post-harvest state, fallback state, news/catalyst availability, ML shadow counts, and the repo-native advisory coaches.
- Does not scan, trade, resize, or change authority.
- Included in `/paper/self-check` output.

Expected visible self-check lines include:

```text
ML shadow counts: rows=6000, labeled=2700, observed_outcomes=49, predictions=25, phase3a_ready=False.
Trade Quality Coach: ...
Risk Coach: ...
Post-Harvest Coach: ...
```

### One-link self-check policy

File:

- `one_link_check.py`

Current purpose:

- Keep `/paper/self-check` as the only routine test link.
- Hide verbose link lists unless `SELF_CHECK_VERBOSE_LINKS=1`.
- Promote important diagnostics into the mobile-safe self-check summary.
- Preserve `copy_paste_links_separate` as only the self-check link by default.

### News / catalyst advisory layer

File:

- `news_sentiment_engine.py`

Current purpose:

- Advisory-only news/catalyst visibility.
- News/catalyst layer is available in latest self-check summaries.
- Should not be used as a standalone trading trigger yet.
- Future use: score support, guardrail, journal context, and catalyst review.

### ML Phase 2 shadow learning

Files:

- `ml_phase2_shadow.py`
- `ml_phase25_readiness.py`

Current status:

- ML is shadow-only.
- `live_trade_decider: false`.
- ML does not place trades.
- ML does not override risk controls.
- ML does not override entries or exits.

Latest known ML2 counts from 2026-06-03:

- Rows total: `6000`
- Labeled outcome rows: `2700`
- Trade outcomes: `49`
- Latest predictions: `25`
- Baseline win rate: `0.8111`
- Readiness: `developing_shadow_model`
- Phase: `phase_2_shadow_learning`
- Phase 3A ready: `false`

Latest known Phase 2.5 readiness:

- Execution rows: `82 / 150` gate failing
- Labeled outcomes: `2700 / 150` passing
- Scanner decisions: `6000 / 5000` passing
- Profit factor: `9.068 / 1.15` passing
- Win rate: `0.6939 / 0.48` passing
- Regime coverage: `2 / 3` failing
- Walk-forward proxy days: `13 / 10` passing
- Formal walk-forward validation: `false` failing
- MAE/MFE telemetry complete: `false` failing
- Gates passed: `5`
- Gates failed: `4`

Current ML recommendation:

- Keep ML shadow-only.
- Continue collecting execution rows and observed outcomes.
- Add/verify MAE/MFE telemetry.
- Add formal walk-forward validation.
- Require Phase 3A readiness before any live ML weighting.

## Update ledger

Use this ledger for future update continuity. Add newest entries at the top.

### 2026-06-04 — Internal advisory coaches added to decision audit

- Commit `8fd184368b1bcc40cc9d174f3eb6bac327b1c2ca` — added Trade Quality Coach, Risk Coach, and Post-Harvest Coach inside `decision_audit_consolidation.py`.
- Files changed: `decision_audit_consolidation.py`, `PROJECT_HANDOFF.md`.
- Reason: add repo-native advisory agents without external API keys or new accounts.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: preserved; advisory coach text should appear inside `decision_audit_next_actions` from `/paper/self-check`.
- Latest known test before this push: `/paper/self-check` passed with decision audit and ML count visibility.
- Next planned focus: verify the advisory coach lines in `/paper/self-check`, then continue toward MAE/MFE telemetry and formal walk-forward validation.

### 2026-06-03 — Added project handoff and recommendation tracking

- Commit `74df666536fd699a7ce73c7a8e69203cd9928006` — added `PROJECT_HANDOFF.md`.
- Commit `d061946dcbb4f42fc28350da213477ceb8fa4fc6` — added handoff maintenance protocol and recommendation/advisory source list.
- This update adds the handoff maintenance protocol and recommendation/advisory source list.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.
- Next planned focus: MAE/MFE telemetry, formal walk-forward validation, and Phase 3A readiness gates.

### 2026-06-03 — ML shadow counts surfaced in one-test path

- Commit `0d30626f040d3fadc5f1d9db09335ee6130d289d` — surfaced ML shadow counts in decision audit.
- Commit `a4097743652ecf657b60709b653663a8c57b3d97` — showed ML shadow counts in one-test next actions.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: preserved.

### 2026-06-03 — Decision audit added to one-test workflow

- Commit `eb9608900d58b5937954d84cf6145fc5f4b3dda6` — added compact decision audit consolidation.
- Commit `edbee88fb3528b159a3f00e9d764f923d7c44511` — included decision audit in one-test startup path.
- Commit `21afb52885053dce6c64f4725fc515f12b9a2faa` — surfaced decision audit in one-test self-check.
- Commit `c4fed90d3a14b8eb24f097711090017de7636ca0` — treated final close lock as protective decision-audit pass.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: enhanced, still one routine link.

### 2026-06-03 — Post-harvest redeployment hardening

- Commit `2322947c4c8bf25d2d60d4ef899bb1d250b04062` — hardened post-harvest redeployment controller.
- Commit `a058a7e1844b12e553dc4e8fda158ba7fdb7c29c` — bridged post-harvest starter entries through profit pause.
- Commit `845f656bf20a3b1462e4834d06c281dab85dfda1` — added guarded post-harvest entry fallback.
- Commit `e1a20eeba2281bb7710714303930ec726be8207b` — wired post-harvest entry fallback into startup.
- Trading authority changed: no forced authority; entries still go through safety/quality checks.
- ML authority changed: no.
- Risk controls changed: no bypasses added.
- One-test workflow changed: no.

## Recent important commits

Recent successful commits from the handoff period:

- `8fd184368b1bcc40cc9d174f3eb6bac327b1c2ca` — added internal advisory coaches to decision audit.
- `d061946dcbb4f42fc28350da213477ceb8fa4fc6` — added handoff update ledger and recommendation sources.
- `74df666536fd699a7ce73c7a8e69203cd9928006` — added initial project handoff file.
- `a4097743652ecf657b60709b653663a8c57b3d97` — showed ML shadow counts in one-test next actions.
- `0d30626f040d3fadc5f1d9db09335ee6130d289d` — surfaced ML shadow counts in decision audit.
- `c4fed90d3a14b8eb24f097711090017de7636ca0` — treated final close lock as protective decision-audit pass.
- `21afb52885053dce6c64f4725fc515f12b9a2faa` — surfaced decision audit in one-test self-check.
- `edbee88fb3528b159a3f00e9d764f923d7c44511` — included decision audit in one-test startup path.
- `eb9608900d58b5937954d84cf6145fc5f4b3dda6` — added compact decision audit consolidation.
- `e1a20eeba2281bb7710714303930ec726be8207b` — wired post-harvest entry fallback into startup.
- `845f656bf20a3b1462e4834d06c281dab85dfda1` — added guarded post-harvest entry fallback.
- `a058a7e1844b12e553dc4e8fda158ba7fdb7c29c` — bridged post-harvest starter entries through profit pause.
- `2322947c4c8bf25d2d60d4ef899bb1d250b04062` — hardened post-harvest redeployment controller.

## Current upgrade plan

### Immediate next priorities

1. Run `/paper/self-check` after the advisory coach push and verify the three coach lines are visible in `decision_audit_next_actions`.
2. Keep monitoring `/paper/self-check` only after pushes.
3. Verify ML count line remains visible in `decision_audit_next_actions`.
4. Continue collecting execution outcomes until at least `150` execution rows.
5. Improve or verify MAE/MFE telemetry; current readiness says MAE/MFE fields are ready but no rows have MAE/MFE yet.
6. Add formal walk-forward validation tooling before any Phase 3A live ML weighting.
7. Expand regime coverage from `2` to at least `3` regimes.
8. Promote important recommendation text from deeper advisory endpoints into `decision_audit_next_actions` when it affects the next development decision.

### Do not do yet

- Do not let ML control trades.
- Do not lower post-harvest thresholds just because cash is high.
- Do not loosen final-close protection.
- Do not bypass self-defense or risk controls.
- Do not require multiple routine test links again.

## New-chat startup instructions

When starting a new ChatGPT session, use this prompt:

```text
Please continue my automated trading bot project.

Repo: sterlingfancher-cmyk/Trading-bot
Railway base URL: https://trading-bot-clean.up.railway.app
Routine test rule: only use /paper/self-check after normal pushes. Do not ask me to run multiple test links unless debugging a specific issue.

Before making changes:
1. Review PROJECT_HANDOFF.md.
2. Review recent GitHub commits.
3. Preserve the one-test workflow.
4. Do not loosen risk controls or give ML live trade authority without explicit approval.
5. Review the recommendation/advisory sources listed in PROJECT_HANDOFF.md before choosing the next update.

Current direction:
- ML remains shadow-only.
- Post-harvest redeployment is active.
- Decision audit is included in /paper/self-check.
- ML shadow counts are surfaced in /paper/self-check.
- Internal advisory coaches are now included in decision_audit_next_actions.
- Next upgrades should focus on feature journal quality, MAE/MFE telemetry, formal walk-forward validation, and Phase 3A readiness gates.
```

## Post-update checklist for future assistants

After any normal code push:

1. Tell the operator to run only:

```text
https://trading-bot-clean.up.railway.app/paper/self-check
```

2. Confirm the result includes:

- `overall: pass`
- `status: ok`
- `decision_audit_overall: pass` when no issue is present
- ML shadow count line in `decision_audit_next_actions`
- Trade Quality Coach line in `decision_audit_next_actions`
- Risk Coach line in `decision_audit_next_actions`
- Post-Harvest Coach line in `decision_audit_next_actions`
- `routine_test_policy.extra_links_required: false`

3. Only request deeper diagnostic links when `/paper/self-check` shows a warning/failure or when debugging a specific module.

4. Update this handoff file with:

- commit SHA
- files changed
- test result
- changed authority, if any
- next planned update
