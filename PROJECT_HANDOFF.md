# Automated Trading Bot Project Handoff

Last updated: 2026-06-04

This file is the continuity source of truth for future ChatGPT sessions. New chats should read this file, inspect recent GitHub commits, and continue without asking the operator to reconstruct prior conversations.

## Repository and deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Main app file: `app.py`
- WSGI startup: `wsgi.py`
- Runtime auxiliary wiring: `usercustomize.py`
- Persistent Railway state: `/data/state.json`
- Routine test link: `https://trading-bot-clean.up.railway.app/paper/self-check`

## Operator preferences and rules

- Preserve the one-test workflow.
- After normal pushes, ask the operator to run only `/paper/self-check`.
- Do not require multiple routine test links unless debugging a specific issue.
- Prefer direct GitHub updates or full-file-safe updates over patch fragments.
- Proactively recommend high-value, low-risk updates when they improve diagnostics, ML readiness, safety, or continuity.
- Do not loosen risk controls without explicit approval.
- Do not give ML live trade authority without explicit approval and promotion-gate evidence.
- Keep manual `/paper/run` protected by `RUN_KEY`.
- Keep this handoff updated after meaningful code changes, test results, or strategy-direction changes.

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

Do not make heavy diagnostic routes part of routine testing.

## Current high-level bot state

Most recent known self-check state from 2026-06-04 13:52 CDT after the feature-journal/regime-tagging push:

- Self-check: `overall: pass`, `status: ok`, `warnings: []`
- Decision audit: `pass`, `status: ok`
- Decision audit version: `decision-audit-consolidation-2026-06-04-v6-chief-advisory-coach`
- Equity: about `$11,015.93`
- Total gain from `$10,000`: about `+10.16%`
- Cash: about `$9,672.49`
- Cash percentage: about `87.80%`
- Open positions: `3`
- Positions: `DELL`, `QQQ`, `SNDK`
- Realized today: `$0.00`
- Realized total: `$857.68`
- Unrealized P&L: about `$158.26`
- Daily loss/drawdown: about `0.073% / 0.119%`
- Self-defense: inactive; reason `feedback loop clear`
- Losses today: `0`
- Scanner signals: `54`
- Blocked entries: `1`
- Top blocked symbol: `TEM`
- Post-harvest outcome: `blocked`
- Post-harvest reason: `post_harvest_controlled_redeployment_candidates`
- ML shadow rows: `6000`
- ML labeled outcome rows: about `2281`
- ML observed outcomes: `49`
- ML latest predictions: `25`
- Phase 3A ready: `false`
- Chief Advisory Coach remains active and still prioritizes MAE/MFE telemetry, formal walk-forward validation, regime coverage, and execution-row collection before Phase 3A.

## Deployment note from 2026-06-04

Railway sent a failed-build email, but the build/deploy logs provided by the operator showed a successful image build and a successful Gunicorn startup:

```text
Starting gunicorn 26.0.0
Listening at: http://0.0.0.0:8080
Booting worker with pid: 2
```

The only runtime issue shown was transient market-data download failures:

```text
['DDOG']: SSLError('Failed to perform, curl: (35) Recv failure: Connection reset by peer...')
['ARM']: SSLError('Failed to perform, curl: (35) Recv failure: Connection reset by peer...')
```

Current interpretation: this is a temporary data-provider/network failure for specific tickers, not a Railway build failure, app crash, or broken deployment. Do not patch or roll back solely for this unless self-check fails or the same ticker-download errors become persistent and degrade scanner behavior.

## Active modules and status

### Core trading engine

- `app.py` owns market regime, scanner, entries, exits, portfolio state, risk controls, `/paper/run`, and `/paper/status`.
- Persistent state is stored under `/data/state.json` on Railway.
- `/paper/run` requires `RUN_KEY`; preferred auth is `X-Run-Key` header.

### Post-harvest redeployment

Files:

- `post_harvest_redeployment_controller.py`
- `post_harvest_entry_fallback.py`

Purpose:

- Detect underdeployment after profit harvesting.
- Redeploy only through 1-2 high-quality starter candidates.
- Keep `max_positions` unchanged.
- Do not bypass halts, stop losses, self-defense, risk controls, or normal entry-quality checks.
- Do not force entries.
- Do not rebuy recently harvested symbols unless they requalify strongly.

Recent posture: underdeployed but selective. Do not lower thresholds blindly.

### Decision audit and advisory coaches

File:

- `decision_audit_consolidation.py`

Current expected version:

```text
decision-audit-consolidation-2026-06-04-v6-chief-advisory-coach
```

Purpose:

- Read-only advisory layer.
- Consolidates scanner/result flow, post-harvest state, fallback state, news/catalyst availability, ML shadow counts, repo-native advisory coaches, and Chief Advisory Coach synthesis.
- Does not scan, trade, resize, or change authority.
- Included in `/paper/self-check` output.

Expected visible self-check lines:

```text
Chief Advisory Coach: highest priority is ...
Trade Quality Coach: ...
Risk Coach: ...
Post-Harvest Coach: ...
ML shadow counts: ...
```

Advisory coaches:

- Trade Quality Coach: reviews execution rows, exits, win/loss quality, profit factor, exit reasons, and symbol-level realized P&L.
- Risk Coach: reviews cash percentage, position count, drawdown, halts, and self-defense state.
- Post-Harvest Coach: reviews post-harvest redeployment posture, underdeployment, qualifying candidates, and whether standing down is appropriate.
- Chief Advisory Coach: analyzes lower-level coaches plus ML shadow state and news/catalyst availability to produce a prioritized action plan.

All coaches are read-only and advisory-only. They do not trade, resize, change risk rules, change ML authority, modify post-harvest thresholds, or override self-defense.

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
- `ml_feature_journal_quality.py`

Current status:

- ML is shadow-only.
- `live_trade_decider: false`.
- ML does not place trades.
- ML does not override risk controls.
- ML does not override entries or exits.
- Latest visible self-check values: rows `6000`, labeled about `2281`, observed outcomes `49`, predictions `25`, Phase 3A ready `false`.

### Feature journal quality and regime tagging

Files:

- `ml_feature_journal_quality.py`
- `wsgi.py`

Current expected version:

```text
ml-feature-journal-quality-2026-06-04-v2-post-ml2-enrichment
```

Purpose:

- Enrich ML2 dataset rows after ML2 creates/refreshed rows.
- Normalize missing or vague regime labels into `bull`, `neutral`, or `bear` when context supports it.
- Add `regime_family`, `regime_subtype`, and `regime_signature` fields for better regime analysis.
- Add `signal_cluster` tags such as `ai_data_center_compute`, `bitcoin_ai_compute`, `precious_metals_defensive`, `mega_cap_growth`, `benchmark_index`, and others.
- Add `risk_state`, `cash_pct_at_log`, `positions_count_at_log`, `underdeployed_at_log`, and `market_clean_for_entries` fields.
- Add feature-quality metadata including `feature_quality_score`, `feature_quality`, and missing-field lists.
- Add optional deeper routes: `/paper/ml-feature-journal-status` and `/paper/regime-tagging-status`.
- Preserve one-test workflow; these routes are optional diagnostics only.
- Keep all outputs advisory-only.
- Do not invent trade outcomes, synthetic MAE/MFE values, or grant ML authority.

Note: `/data/state.json` increased to about `16.86 MB` after enrichment. This is not currently failing, but future chats should monitor state size and consider feature-journal compaction if growth continues.

### MAE/MFE telemetry and formal walk-forward validation

Files:

- `intratrade_path_capture.py`
- `mae_mfe_integration.py`
- `ml_phase25_readiness.py`

Current expected versions:

```text
mae-mfe-integration-2026-06-04-telemetry-complete
ml-phase25-readiness-2026-06-04-formal-wf-mae-mfe
```

Purpose:

- Refresh real intratrade path telemetry from open positions.
- Archive closed-path telemetry when positions close.
- Convert real MAE/MFE path telemetry into feature rows for ML and trade-quality review.
- Enrich ML2 dataset rows and realized trade rows when matching real path telemetry exists.
- Add formal chronological walk-forward validation using realized exit rows.
- Keep all outputs advisory-only.
- Do not invent synthetic MAE/MFE values.
- Do not grant ML authority.

## Optional deeper diagnostic routes

Use only when `/paper/self-check` indicates a warning/failure or when choosing the next major upgrade:

```text
/paper/ml2-status
/paper/ml-readiness-status
/paper/ml-phase25-status
/paper/ml-feature-journal-status
/paper/regime-tagging-status
/paper/mae-mfe-integration-status
/paper/intratrade-path-status
/paper/position-path-status
/paper/decision-audit-status
/paper/no-entry-diagnostic
/paper/risk-on-entry-diagnostic
/paper/strategy-promotion-readiness-status
/paper/strategy-scorecard-status
/paper/news-sentiment-status
/paper/catalyst-watchlist
/paper/news-risk-status
/paper/market-extension-status
/paper/risk-reward-status
/paper/adaptive-ml-status
/paper/adaptive-portfolio-status
```

Do not make these part of routine testing.

## Proactive recommendation policy

Future assistants should recommend additional high-value, low-risk updates before the operator has to ask, as long as the recommendation is clearly labeled and does not silently change authority.

Good proactive recommendations include better observability inside `/paper/self-check`, internal advisory coaches, MAE/MFE telemetry, formal walk-forward validation, feature-journal quality improvements, safer readiness gates, handoff/continuity improvements, clearer diagnostics for blocked/rejected/no-decision trades, data-provider resilience, and state-size compaction.

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

Current priority remains trading-system quality first: MAE/MFE telemetry, formal walk-forward validation, execution outcome collection, regime coverage, state-size stability, and Phase 3A readiness gates.

## Update ledger

Use this ledger for future update continuity. Add newest entries at the top.

### 2026-06-04 — Feature-journal post-push self-check passed; transient data-feed errors noted

- Files changed in this ledger update: `PROJECT_HANDOFF.md`.
- Reason: record successful post-feature-journal `/paper/self-check` and note Railway runtime data-provider warnings.
- Latest test: `overall: pass`, `status: ok`, `warnings: []`, decision audit `pass`, 3 positions, equity about `$11,015.93`, cash about `87.80%`, no self-defense, no losses today, 54 signals, 1 blocked entry, post-harvest candidate `TEM` blocked, ML still shadow-only.
- Deployment note: Railway build/deploy appears healthy; DDOG/ARM SSL messages are transient ticker-download/data-feed failures rather than app startup failures.
- State size note: `/data/state.json` about `16.86 MB`; monitor after feature-journal enrichment and consider compaction if growth continues.
- Trading authority changed: no.
- ML authority changed: no; Phase 3A remains false.
- Risk controls changed: no.
- One-test workflow changed: no.
- Next planned focus: continue collecting execution rows toward `150`, monitor data-provider resilience and state-size growth, and inspect `/paper/ml-feature-journal-status` only if deeper feature-journal detail is needed.

### 2026-06-04 — Feature journal quality and regime tagging added

- Commit `726dd35bb9a6b9bf8b0d3ce43f45a978845b4403` — created `ml_feature_journal_quality.py`.
- Commit `df2ee8e3938e0323028d548200c8f33c2a98cdb6` — hardened feature journal enrichment to run after ML2 row refresh.
- Commit `cfb151b244fe093a933ce45e2e1229d0e1424abe` — wired `ml_feature_journal_quality.py` into `wsgi.py` and added optional diagnostic routes to light endpoint registration.
- Commit `c5cc65ae1bec0f5ca5b88560e1be6d52301a64cc` — updated `PROJECT_HANDOFF.md` with feature-journal notes.
- Files changed: `ml_feature_journal_quality.py`, `wsgi.py`, `PROJECT_HANDOFF.md`.
- Reason: improve ML feature-journal quality, normalize regime tagging, and add richer regime/cluster/risk-state metadata without changing trading authority.
- Trading authority changed: no.
- ML authority changed: no; ML remains shadow-only.
- Risk controls changed: no.
- One-test workflow changed: no; optional routes are deeper diagnostics only.

### 2026-06-04 — Post-update self-check passed after MAE/MFE and walk-forward push

- Commit `0688db61dea79f0b7c48f12ee35b033b3ac24603` — logged successful post-update `/paper/self-check` result.
- Latest test: `overall: pass`, `status: ok`, `warnings: []`, decision audit `pass`, 3 positions, equity about `$10,997.42`, cash about `87.95%`, no self-defense, no losses today, 31 signals, 15 blocked entries.
- Trading authority changed: no.
- ML authority changed: no; Phase 3A remains false.
- Risk controls changed: no.
- One-test workflow changed: no.

### 2026-06-04 — MAE/MFE telemetry and formal walk-forward validation upgraded

- Commit `00b25cb8f8927ff545f29821c2430e56b9c80e95` — updated `ml_phase25_readiness.py` with formal chronological walk-forward validation and real MAE/MFE readiness validation.
- Commit `f405c2a0582e779a9722fcf73b131632b3c3db2a` — updated `mae_mfe_integration.py` to refresh intratrade path capture, enrich ML/trade rows from real path telemetry, and expose telemetry counts.
- Commit `53275b01aa7654c5ed05a6f2de1dbab6260ae139` — updated `PROJECT_HANDOFF.md` with the MAE/MFE and walk-forward upgrade notes.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.

### 2026-06-04 — Chief Advisory Coach added

- Commit `49ede794ad1de0cd2a16ae487fb28ace103913b0` — added Chief Advisory Coach synthesis to `decision_audit_consolidation.py`.
- Commit `51a9cd2f6912af04a65650157c89757dde594a25` — documented Chief Advisory Coach in `PROJECT_HANDOFF.md`.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: preserved.

### 2026-06-04 — Productization roadmap documented

- Commit `a83a88f924694ac74a43ab971c3081557e82258c` — added commercial/productization roadmap to `PROJECT_HANDOFF.md`.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.

### 2026-06-04 — Proactive update recommendation preference recorded

- Commit `929d4b27c1e70cd78f8d0c3e80f133ddd3482911` — recorded proactive update recommendation preference in `PROJECT_HANDOFF.md`.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.

### 2026-06-04 — Internal advisory coaches added to decision audit

- Commit `8fd184368b1bcc40cc9d174f3eb6bac327b1c2ca` — added Trade Quality Coach, Risk Coach, and Post-Harvest Coach inside `decision_audit_consolidation.py`.
- Commit `6a0678de506240cf7de051f233abf98968a63ae2` — logged internal advisory coaches in `PROJECT_HANDOFF.md`.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: preserved.

### 2026-06-03 — ML shadow counts surfaced in one-test path

- Commit `0d30626f040d3fadc5f1d9db09335ee6130d289d` — surfaced ML shadow counts in decision audit.
- Commit `a4097743652ecf657b60709b653663a8c57b3d97` — showed ML shadow counts in one-test next actions.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: preserved.

### 2026-06-03 — Post-harvest redeployment hardening

- Commit `2322947c4c8bf25d2d60d4ef899bb1d250b04062` — hardened post-harvest redeployment controller.
- Commit `a058a7e1844b12e553dc4e8fda158ba7fdb7c29c` — bridged post-harvest starter entries through profit pause.
- Commit `845f656bf20a3b1462e4834d06c281dab85dfda1` — added guarded post-harvest entry fallback.
- Commit `e1a20eeba2281bb7710714303930ec726be8207b` — wired post-harvest entry fallback into startup.
- Trading authority changed: no forced authority; entries still go through safety/quality checks.
- ML authority changed: no.
- Risk controls changed: no bypasses added.
- One-test workflow changed: no.

## Current upgrade plan

### Immediate next priorities

1. Keep ML shadow-only.
2. Continue collecting execution outcomes until at least `150` execution rows.
3. Monitor whether feature-journal quality and regime tags improve readiness visibility after normal bot cycles.
4. Monitor state size after feature-journal enrichment. If `/data/state.json` keeps growing quickly, prioritize state-size compaction/retention before more feature expansion.
5. Monitor transient data-provider errors. If repeated ticker SSL failures persist, add a data-fetch resilience layer with retries/backoff and warning aggregation.
6. Use `/paper/ml-feature-journal-status` only if deeper feature-journal detail is needed.
7. Use `/paper/ml-readiness-status` only if deeper readiness-gate inspection is needed.
8. Continue expanding true regime coverage from `2` to at least `3` regimes. Derived tags help visibility but do not alone justify Phase 3A promotion.
9. Preserve the productization path for later dashboard/demo/reporting work, but keep current priority on trading quality, telemetry, validation, and state stability.

### Do not do yet

- Do not let ML control trades.
- Do not lower post-harvest thresholds just because cash is high.
- Do not loosen final-close protection.
- Do not bypass self-defense or risk controls.
- Do not require multiple routine test links again.
- Do not build live multi-user brokerage automation before legal/compliance review.

## New-chat startup instructions

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
- MAE/MFE telemetry integration and formal walk-forward validation are upgraded.
- ML feature-journal quality and regime tagging are added as advisory-only readiness/diagnostic layers.
- Latest self-check after the feature-journal push passed.
- DDOG/ARM SSL download errors appeared in runtime logs but self-check passed; treat as transient data-feed warnings unless persistent.
- State size reached about 16.86 MB after feature-journal enrichment; monitor for growth and consider compaction if needed.
- Commercial path is documented as a future web-based/paper-trading analytics dashboard first.
- Next upgrades should focus on execution outcome collection, true regime coverage, Phase 3A readiness gates, data-feed resilience if needed, and state-size stability.
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

4. Update this handoff file with commit SHA, files changed, test result, changed authority if any, and next planned update.
