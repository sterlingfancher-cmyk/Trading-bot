# Automated Trading Bot Project Handoff

Last updated: 2026-06-04

This file is the project continuity source of truth for future ChatGPT sessions. New chats should read this file, inspect recent GitHub commits, and continue without asking the operator to reconstruct prior conversations.

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
- Proactively recommend high-value, low-risk updates when they improve diagnostics, ML readiness, safety, or continuity, especially when they preserve trading authority, ML authority, risk controls, and the one-test workflow.
- Do not loosen risk controls without explicit approval.
- Do not give ML live trade authority without explicit approval and promotion-gate evidence.
- Keep manual `/paper/run` protected by `RUN_KEY`.
- Keep this handoff updated after meaningful code changes, test results, or strategy-direction changes.

## Handoff maintenance protocol

Every future assistant should treat this file as a living project ledger. After any meaningful update, append or refresh the relevant sections below.

Update this file when any of the following happens:

1. A code change is pushed.
2. A self-check result changes the known bot state.
3. A new module, route, endpoint, risk rule, or advisory layer is added.
4. A bug is found or resolved.
5. A new next-step priority is chosen.
6. ML readiness gates change.
7. The one-test workflow changes.

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

Permanent rule: if a future chat changes GitHub but does not update this file, the next chat should consider the handoff stale and inspect recent commits before making assumptions.

## Recommendation and advisory sources to review

Primary routine source:

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

Known advisory/recommendation modules:

- `decision_audit_consolidation.py` — compact decision audit, post-harvest status, news availability, ML shadow counts, internal advisory coaches, and Chief Advisory Coach synthesis.
- `risk_on_recommendation_cleanup.py` — cleans/deduplicates risk-on recommendation text and accelerator feedback.
- `risk_on_entry_diagnostic.py` — risk-on entry diagnostics and candidate reasoning.
- `entry_decision_visibility.py` — entered/blocked/skipped/no-decision behavior.
- `ml_phase2_shadow.py` — ML shadow predictions and recommendation text; never live-authoritative.
- `ml_phase25_readiness.py` — Phase 2.5/Phase 3A readiness gates.
- `mae_mfe_integration.py` — MAE/MFE telemetry readiness.
- `news_sentiment_engine.py` — news/catalyst advisory context.
- `market_extension_guard.py` — market extension/overextension advisories.
- `benchmark_participation.py` — benchmark/risk-on participation diagnostics.
- `adaptive_ml_research.py` — adaptive ML research recommendations.
- `adaptive_portfolio_intelligence.py` — portfolio intelligence/advisory recommendations.
- `strategy_promotion_readiness.py` — strategy promotion gates.
- `strategy_scorecard.py` — strategy scorecards and performance comparisons.
- `trade_quality_telemetry.py` — trade-quality telemetry and improvement signals.

Optional deeper diagnostic routes, only when `/paper/self-check` indicates a warning/failure or when choosing the next major upgrade:

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

## Internal advisory coaches

As of 2026-06-04, the repo-native advisory coaches are implemented inside `decision_audit_consolidation.py` and are surfaced through `/paper/self-check` via `decision_audit_next_actions`.

- Trade Quality Coach: reviews execution rows, exits, win/loss quality, profit factor, exit reasons, and symbol-level realized P&L.
- Risk Coach: reviews cash percentage, position count, drawdown, halts, and self-defense state.
- Post-Harvest Coach: reviews post-harvest redeployment posture, underdeployment, qualifying candidates, and whether standing down is appropriate.
- Chief Advisory Coach: analyzes the Trade Quality Coach, Risk Coach, Post-Harvest Coach, ML shadow state, and news/catalyst availability to produce a prioritized action plan.

All coaches are read-only and advisory-only. They do not trade, resize, change risk rules, change ML authority, modify post-harvest thresholds, or override self-defense.

Expected visible self-check lines include:

```text
Chief Advisory Coach: highest priority is ...
Trade Quality Coach: ...
Risk Coach: ...
Post-Harvest Coach: ...
ML shadow counts: rows=6000, labeled=2700, observed_outcomes=49, predictions=25, phase3a_ready=False.
```

## Proactive recommendation policy

Future assistants should recommend additional high-value, low-risk updates before the operator has to ask, as long as the recommendation is clearly labeled and does not silently change authority.

Good proactive recommendations include:

- better observability inside `/paper/self-check`
- internal advisory coaches
- MAE/MFE telemetry improvements
- formal walk-forward validation
- feature-journal quality improvements
- safer readiness gates
- handoff/continuity improvements
- clearer diagnostics for blocked, rejected, or no-decision trades

Do not proactively implement changes that loosen risk controls, grant ML live authority, lower post-harvest thresholds, bypass self-defense, or change trade execution authority without explicit operator approval.

## Commercial/productization roadmap

The operator eventually wants a path to make the system profitable by selling access to the platform, code, dashboard, reports, or app-style experience.

The safest first commercial product should be a web-based/app-style trading intelligence and paper-trading analytics platform, not an auto-trading product that controls other users' live brokerage accounts.

Initial positioning:

```text
Trading intelligence dashboard with paper-trading, risk analytics, ML shadow rankings, scanner diagnostics, decision explanations, and performance reporting.
```

Avoid positioning it as:

```text
Guaranteed AI auto-trading system that makes money for users.
```

Commercial roadmap:

1. Web dashboard / paper analytics product: status cards, scanner rankings, model portfolio, coach summaries, performance reports, demo mode, and no broker connectivity.
2. Strategy access and alerts: watchlist rankings, alerts, paper-first model portfolio, manual-copy trade ideas, setup scores, and reports.
3. SaaS architecture: auth, per-user state, admin dashboard, billing, plan limits, public demo, legal pages, audit logs, support workflow, secret management.
4. Live automation only after legal/compliance review. Do not build multi-user broker-connected live trading as the first commercial product.

Possible pricing ideas to revisit later:

- basic dashboard: `$19-$49/month`
- pro dashboard plus alerts: `$79-$149/month`
- advanced analytics/reporting: `$199+/month`
- one-time code/template license: `$299-$999`
- setup/coaching package: `$500-$2,500`
- white-label/private workspace: later-stage pricing only

Current priority remains trading-system quality first: MAE/MFE telemetry, formal walk-forward validation, execution outcome collection, regime coverage, and Phase 3A readiness gates.

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
- Mobile-safe mode may only internally check `/health` and `/paper/status`, but it promotes compact summaries from decision audit, advisory coaches, and ML counts into the payload.

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
- Self-defense: inactive in the latest status; final-close lock was previously recognized correctly as protective rather than a warning
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

Purpose:

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

```text
decision-audit-consolidation-2026-06-04-v6-chief-advisory-coach
```

Purpose:

- Read-only advisory layer.
- Consolidates scanner/result flow, post-harvest state, fallback state, news/catalyst availability, ML shadow counts, repo-native advisory coaches, and Chief Advisory Coach synthesis.
- Does not scan, trade, resize, or change authority.
- Included in `/paper/self-check` output.

### One-link self-check policy

File:

- `one_link_check.py`

Purpose:

- Keep `/paper/self-check` as the only routine test link.
- Hide verbose link lists unless `SELF_CHECK_VERBOSE_LINKS=1`.
- Promote important diagnostics into the mobile-safe self-check summary.
- Preserve `copy_paste_links_separate` as only the self-check link by default.

### News / catalyst advisory layer

File:

- `news_sentiment_engine.py`

Purpose:

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

### 2026-06-04 — Chief Advisory Coach added

- Commit `49ede794ad1de0cd2a16ae487fb28ace103913b0` — added Chief Advisory Coach synthesis to `decision_audit_consolidation.py`.
- Files changed: `decision_audit_consolidation.py`, `PROJECT_HANDOFF.md`.
- Reason: synthesize Trade Quality Coach, Risk Coach, Post-Harvest Coach, ML shadow state, and news/catalyst availability into a prioritized action plan.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: preserved; Chief Advisory Coach text should appear inside `decision_audit_next_actions` from `/paper/self-check`.
- Latest known test before this push: `/paper/self-check` passed with decision audit and ML count visibility.
- Next planned focus: verify Chief Advisory Coach line in `/paper/self-check`, then continue toward MAE/MFE telemetry and formal walk-forward validation.

### 2026-06-04 — Productization roadmap documented

- Commit `a83a88f924694ac74a43ab971c3081557e82258c` — added commercial/productization roadmap to `PROJECT_HANDOFF.md`.
- Files changed: `PROJECT_HANDOFF.md`.
- Reason: document future monetization path around a web-based/paper-trading analytics platform first, with live account automation treated as a later compliance-reviewed phase.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.
- Next planned focus: keep trading-system quality first while preserving the productization path for later dashboard/demo/reporting work.

### 2026-06-04 — Proactive update recommendation preference recorded

- Commit `929d4b27c1e70cd78f8d0c3e80f133ddd3482911` — recorded proactive update recommendation preference in `PROJECT_HANDOFF.md`.
- Files changed: `PROJECT_HANDOFF.md`.
- Reason: operator wants future assistants to proactively recommend high-value, low-risk updates like internal advisory coaches instead of waiting for direct prompting.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.
- Next planned focus: continue recommending safe observability, readiness, and advisory improvements before implementation.

### 2026-06-04 — Internal advisory coaches added to decision audit

- Commit `8fd184368b1bcc40cc9d174f3eb6bac327b1c2ca` — added Trade Quality Coach, Risk Coach, and Post-Harvest Coach inside `decision_audit_consolidation.py`.
- Commit `6a0678de506240cf7de051f233abf98968a63ae2` — logged internal advisory coaches in `PROJECT_HANDOFF.md`.
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

- `49ede794ad1de0cd2a16ae487fb28ace103913b0` — added Chief Advisory Coach synthesis.
- `a83a88f924694ac74a43ab971c3081557e82258c` — added productization roadmap to handoff.
- `929d4b27c1e70cd78f8d0c3e80f133ddd3482911` — recorded proactive update recommendation preference.
- `8fd184368b1bcc40cc9d174f3eb6bac327b1c2ca` — added internal advisory coaches to decision audit.
- `6a0678de506240cf7de051f233abf98968a63ae2` — logged internal advisory coaches in handoff.
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

1. Run `/paper/self-check` after the Chief Advisory Coach push and verify the Chief Advisory Coach line is visible in `decision_audit_next_actions`.
2. Keep monitoring `/paper/self-check` only after pushes.
3. Verify ML count line and the three lower-level coach lines remain visible in `decision_audit_next_actions`.
4. Continue collecting execution outcomes until at least `150` execution rows.
5. Improve or verify MAE/MFE telemetry; current readiness says MAE/MFE fields are ready but no rows have MAE/MFE yet.
6. Add formal walk-forward validation tooling before any Phase 3A live ML weighting.
7. Expand regime coverage from `2` to at least `3` regimes.
8. Promote important recommendation text from deeper advisory endpoints into `decision_audit_next_actions` when it affects the next development decision.
9. Proactively recommend safe, low-risk observability and readiness upgrades when they are likely to improve the system without changing authority.
10. Preserve the productization path for later dashboard/demo/reporting work, but keep current development priority on trading quality, telemetry, and validation.

### Do not do yet

- Do not let ML control trades.
- Do not lower post-harvest thresholds just because cash is high.
- Do not loosen final-close protection.
- Do not bypass self-defense or risk controls.
- Do not require multiple routine test links again.
- Do not build live multi-user brokerage automation before legal/compliance review.

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
6. Proactively recommend high-value, low-risk updates when they improve observability, safety, readiness, or continuity without changing trading authority.
7. Preserve the productization roadmap: first commercial version should be analytics/paper/dashboard/reporting, not live multi-user brokerage automation.

Current direction:
- ML remains shadow-only.
- Post-harvest redeployment is active.
- Decision audit is included in /paper/self-check.
- ML shadow counts are surfaced in /paper/self-check.
- Internal advisory coaches and Chief Advisory Coach are included in decision_audit_next_actions.
- Future assistants should proactively recommend safe readiness/observability improvements before implementation.
- Commercial path is documented as a future web-based/paper-trading analytics dashboard first.
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
- Chief Advisory Coach line in `decision_audit_next_actions`
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
