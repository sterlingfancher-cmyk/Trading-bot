# Automated Trading Bot Project Handoff

Last updated: 2026-06-03

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

- `decision-audit-consolidation-2026-06-03-v4-ml-counts-visible`

Purpose:

- Read-only advisory layer.
- Consolidates scanner/result flow, post-harvest state, fallback state, news/catalyst availability, and ML shadow counts.
- Does not scan, trade, resize, or change authority.
- Included in `/paper/self-check` output.

Expected visible self-check lines include:

```text
ML shadow counts: rows=6000, labeled=2700, observed_outcomes=49, predictions=25, phase3a_ready=False.
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

## Recent important commits

Recent successful commits from the handoff period:

- `2322947c4c8bf25d2d60d4ef899bb1d250b04062` — hardened post-harvest redeployment controller.
- `a058a7e1844b12e553dc4e8fda158ba7fdb7c29c` — bridged post-harvest starter entries through profit pause.
- `845f656bf20a3b1462e4834d06c281dab85dfda1` — added guarded post-harvest entry fallback.
- `e1a20eeba2281bb7710714303930ec726be8207b` — wired post-harvest entry fallback into startup.
- `eb9608900d58b5937954d84cf6145fc5f4b3dda6` — added compact decision audit consolidation.
- `edbee88fb3528b159a3f00e9d764f923d7c44511` — included decision audit in one-test startup path.
- `21afb52885053dce6c64f4725fc515f12b9a2faa` — surfaced decision audit in one-test self-check.
- `c4fed90d3a14b8eb24f097711090017de7636ca0` — treated final close lock as protective decision-audit pass.
- `0d30626f040d3fadc5f1d9db09335ee6130d289d` — surfaced ML shadow counts in decision audit.
- `a4097743652ecf657b60709b653663a8c57b3d97` — showed ML shadow counts in one-test next actions.

## Current upgrade plan

### Immediate next priorities

1. Keep monitoring `/paper/self-check` only after pushes.
2. Verify ML count line remains visible in `decision_audit_next_actions`.
3. Continue collecting execution outcomes until at least `150` execution rows.
4. Improve or verify MAE/MFE telemetry; current readiness says MAE/MFE fields are ready but no rows have MAE/MFE yet.
5. Add formal walk-forward validation tooling before any Phase 3A live ML weighting.
6. Expand regime coverage from `2` to at least `3` regimes.

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

Current direction:
- ML remains shadow-only.
- Post-harvest redeployment is active.
- Decision audit is included in /paper/self-check.
- ML shadow counts are surfaced in /paper/self-check.
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
- `routine_test_policy.extra_links_required: false`

3. Only request deeper diagnostic links when `/paper/self-check` shows a warning/failure or when debugging a specific module.
