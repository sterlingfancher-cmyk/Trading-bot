# Automated Trading Bot Project Handoff

Last updated: 2026-06-04

This file is the continuity source of truth for future ChatGPT sessions. New chats should read this file, inspect recent GitHub commits, and continue without asking the operator to reconstruct prior conversations.

## Repository and deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Main app file: `app.py`
- WSGI startup: `wsgi.py`
- Persistent Railway state: `/data/state.json`
- Routine test link: `https://trading-bot-clean.up.railway.app/paper/self-check`

## Permanent operating rules

- Preserve the one-test workflow.
- After normal pushes, ask the operator to run only `/paper/self-check`.
- Do not require multiple routine test links unless debugging a specific issue.
- Prefer direct GitHub updates or full-file-safe updates over patch fragments.
- Proactively recommend high-value, low-risk updates when they improve diagnostics, ML readiness, safety, continuity, state stability, or productization planning.
- Do not loosen risk controls without explicit approval.
- Do not give ML live trade authority without explicit approval and promotion-gate evidence.
- Keep manual `/paper/run` protected by `RUN_KEY`.
- Keep this handoff updated after meaningful code changes, test results, strategy-direction changes, or ML readiness-gate changes.

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

## Latest known bot state

Most recent self-check from 2026-06-04 15:26 CDT after the state-size retention push:

- Self-check: `overall: pass`, `status: ok`, `warnings: []`
- Decision audit: `pass`, `status: ok`
- Decision audit version: `decision-audit-consolidation-2026-06-04-v6-chief-advisory-coach`
- Equity: about `$11,001.76`
- Total gain from `$10,000`: about `+10.02%`
- Cash: about `$9,672.49`
- Cash percentage: about `87.92%`
- Open positions: `3`
- Positions: `DELL`, `QQQ`, `SNDK`
- Realized today: `$0.00`
- Realized total: `$857.68`
- Unrealized P&L: about `$144.10`
- Daily/intraday drawdown: about `0.201% / 0.248%`
- Self-defense: inactive; reason `feedback loop clear`
- Losses today: `0`
- Scanner signals: `29`
- Blocked entries: `10`
- Top blocked symbols: `IESC`, `MOD`, `NRG`, `HIVE`, `VRT`, `CEG`, `VST`, `PANW`, `HWM`, `CDE`
- Post-harvest outcome: `no_candidate_qualified`
- Post-harvest reason: `self_defense_active` / protective close lock context
- ML shadow rows: `6000`
- ML labeled outcome rows: about `1823`
- ML observed outcomes: `49`
- ML latest predictions: `25`
- Phase 3A ready: `false`
- State file size: `14,499,209` bytes, down from about `16.86 MB` after feature-journal enrichment.
- Chief Advisory Coach remains active and still prioritizes MAE/MFE telemetry, formal walk-forward validation, regime coverage, and execution-row collection before Phase 3A.

## Deployment/data-feed note from 2026-06-04

Railway sent a failed-build email, but logs provided by the operator showed successful image build and Gunicorn startup. Runtime logs showed transient data-provider SSL download failures for `DDOG` and `ARM`. Current interpretation: temporary ticker-level data-provider/network failure, not a Railway build failure, app crash, or broken deployment. Do not patch or roll back solely for this unless self-check fails or repeated ticker-download errors degrade scanner behavior.

## Active modules and status

### Core trading engine

- `app.py` owns market regime, scanner, entries, exits, portfolio state, risk controls, `/paper/run`, and `/paper/status`.
- Persistent state is stored under `/data/state.json`.
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

Current posture: underdeployed but selective. Do not lower thresholds blindly.

### Decision audit and advisory coaches

File:

- `decision_audit_consolidation.py`

Expected version:

```text
decision-audit-consolidation-2026-06-04-v6-chief-advisory-coach
```

Purpose:

- Read-only advisory layer.
- Consolidates scanner/result flow, post-harvest state, fallback state, news/catalyst availability, ML shadow counts, lower-level advisory coaches, and Chief Advisory Coach synthesis.
- Does not scan, trade, resize, change risk, or change authority.
- Included in `/paper/self-check` output.

Advisory coaches:

- Trade Quality Coach: execution rows, exits, win/loss quality, profit factor, exit reasons, and symbol-level realized P&L.
- Risk Coach: cash percentage, position count, drawdown, halts, and self-defense state.
- Post-Harvest Coach: post-harvest redeployment posture, underdeployment, candidates, and whether standing down is appropriate.
- Chief Advisory Coach: analyzes lower-level coaches plus ML shadow state and news/catalyst availability to produce a prioritized action plan.

All coaches are advisory-only. They do not trade, resize, change risk rules, change ML authority, modify post-harvest thresholds, or override self-defense.

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
- Latest visible self-check values: rows `6000`, labeled about `1823`, observed outcomes `49`, predictions `25`, Phase 3A ready `false`.

### Feature journal quality and regime tagging

Files:

- `ml_feature_journal_quality.py`
- `wsgi.py`

Expected version:

```text
ml-feature-journal-quality-2026-06-04-v2-post-ml2-enrichment
```

Purpose:

- Enrich ML2 dataset rows after ML2 creates/refreshed rows.
- Normalize missing/vague regime labels into `bull`, `neutral`, or `bear` when context supports it.
- Add `regime_family`, `regime_subtype`, `regime_signature`, `signal_cluster`, `risk_state`, `cash_pct_at_log`, `positions_count_at_log`, `underdeployed_at_log`, `market_clean_for_entries`, and feature-quality metadata.
- Add optional deeper routes: `/paper/ml-feature-journal-status` and `/paper/regime-tagging-status`.
- Preserve one-test workflow; deeper routes are optional diagnostics only.
- Keep outputs advisory-only.
- Do not invent trade outcomes, synthetic MAE/MFE values, or grant ML authority.

### MAE/MFE telemetry and formal walk-forward validation

Files:

- `intratrade_path_capture.py`
- `mae_mfe_integration.py`
- `ml_phase25_readiness.py`

Expected versions:

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
- Keep outputs advisory-only.
- Do not invent synthetic MAE/MFE values.
- Do not grant ML authority.

### State-size watchdog and retention policy

File:

- `state_size_watchdog.py`

Expected version after latest update:

```text
state-size-watchdog-2026-06-04-v2-retention-policy
```

Purpose:

- Prevent state bloat after feature-journal/ML telemetry expansion.
- Preserve source-of-truth trading data: cash, equity, peak, positions, trades, risk controls, performance, realized P&L, current reports, and current summaries.
- Compact only derived or duplicated telemetry/diagnostic history.
- Keep full recent ML2 rows while thinning older ML2 dataset rows to core fields.
- Cap scanner lists, report history, MAE/MFE tails, path archives, and advisory tails.
- Generously cap equity history only if it becomes excessive.
- Record `state_size_watchdog` summary inside state including before/after estimated size, actions, thresholds, and retention policy.
- Does not trade, resize, change risk controls, grant ML authority, or change post-harvest thresholds.

Default thresholds:

- Compact trigger: `15 MB`
- Watch: `20 MB`
- Warn: `25 MB`
- Critical: `35 MB`

Important retention settings:

- ML2 dataset max rows: `6000`
- Full recent ML2 rows: `1500`
- Scanner list limit: `100`
- Report history limit: `30`
- Path archive limit: `300`
- Advisory tail limit: `75`
- Equity history generous cap: `2000`
- Trades pruned: `false`
- Positions pruned: `false`
- Risk controls modified: `false`
- ML authority changed: `false`
- Trading authority changed: `false`

Latest result: state-size retention appears successful. `/data/state.json` dropped from about `16.86 MB` to `14,499,209` bytes while self-check remained clean and trade/account state remained intact.

## Optional deeper diagnostic routes

Use only when `/paper/self-check` indicates a warning/failure or when choosing the next major upgrade:

```text
/paper/state-size-watchdog
/paper/telemetry-retention-status
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

## Commercial/productization roadmap

The eventual commercial path is a web-based/app-style trading intelligence and paper-trading analytics platform first, not live broker-connected auto-trading for other users.

Initial positioning:

```text
Trading intelligence dashboard with paper-trading, risk analytics, ML shadow rankings, scanner diagnostics, decision explanations, and performance reporting.
```

Avoid positioning it as guaranteed AI auto-trading or guaranteed profit generation.

Commercial sequence:

1. Web dashboard / paper analytics product.
2. Strategy access and alerts.
3. SaaS architecture: auth, per-user state, billing, admin, demo mode, legal pages, audit logs, support, secret management.
4. Live automation only after legal/compliance review.

Current priority remains trading-system quality first: execution outcome collection, true regime coverage, Phase 3A readiness gates, data-feed resilience if needed, and state-size stability.

## Update ledger

### 2026-06-04 — End-of-day self-check passed after state-size retention

- Files changed in this ledger update: `PROJECT_HANDOFF.md`.
- Reason: record successful EOD `/paper/self-check` after conservative state-size retention update.
- Latest test: `overall: pass`, `status: ok`, `warnings: []`, decision audit `pass`, 3 positions, equity about `$11,001.76`, cash about `87.92%`, no self-defense, no losses today, 29 signals, 10 blocked entries, ML still shadow-only.
- State-size result: `/data/state.json` size was `14,499,209` bytes, down from about `16.86 MB`; compaction/retention appears effective.
- Trading authority changed: no.
- ML authority changed: no; Phase 3A remains false.
- Risk controls changed: no.
- One-test workflow changed: no.
- Next planned focus: continue collecting execution rows toward `150`, true regime coverage, MAE/MFE/walk-forward validation maturity, and optional data-feed resilience if SSL ticker failures persist.

### 2026-06-04 — Conservative state-size retention policy added

- Commit `501f47566495e5e4e08c72b9c62cb74ebb9ca09a` — updated `state_size_watchdog.py` from advisory-only reporting to conservative retention/compaction policy.
- Commit `7f50badf70baca8b6d7a27a92bd234cdfd6d0b7a` — updated handoff with state-size retention details.
- Reason: state file grew to about `16.86 MB` after feature-journal enrichment; add safe compaction before it reaches watch/warn thresholds.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- Post-harvest thresholds changed: no.
- One-test workflow changed: no.
- Data preserved: trades, positions, cash/equity, risk controls, performance, realized P&L, open-state summaries.
- Data compacted only if threshold is reached: old/derived ML rows, scanner lists, report histories, path archives, MAE/MFE/advisory tails, and excessive equity history.

### 2026-06-04 — Feature-journal post-push self-check passed; transient data-feed errors noted

- Commit `c16f8231f7222384081ba31fa75ae23987deb010` — logged successful post-feature-journal `/paper/self-check` and transient DDOG/ARM data-feed errors.
- Latest test: `overall: pass`, `status: ok`, `warnings: []`, decision audit `pass`, 3 positions, equity about `$11,015.93`, cash about `87.80%`, no self-defense, no losses today, 54 signals, 1 blocked entry, post-harvest candidate `TEM` blocked, ML still shadow-only.
- State size note: `/data/state.json` about `16.86 MB`.
- Trading authority changed: no.
- ML authority changed: no; Phase 3A remains false.
- Risk controls changed: no.
- One-test workflow changed: no.

### 2026-06-04 — Feature journal quality and regime tagging added

- Commit `726dd35bb9a6b9bf8b0d3ce43f45a978845b4403` — created `ml_feature_journal_quality.py`.
- Commit `df2ee8e3938e0323028d548200c8f33c2a98cdb6` — hardened feature journal enrichment to run after ML2 row refresh.
- Commit `cfb151b244fe093a933ce45e2e1229d0e1424abe` — wired `ml_feature_journal_quality.py` into `wsgi.py` and optional diagnostics.
- Commit `c5cc65ae1bec0f5ca5b88560e1be6d52301a64cc` — updated handoff.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.

### 2026-06-04 — MAE/MFE telemetry and formal walk-forward validation upgraded

- Commit `00b25cb8f8927ff545f29821c2430e56b9c80e95` — formal chronological walk-forward validation and real MAE/MFE readiness validation.
- Commit `f405c2a0582e779a9722fcf73b131632b3c3db2a` — MAE/MFE integration bridge refresh/enrichment.
- Commit `53275b01aa7654c5ed05a6f2de1dbab6260ae139` — updated handoff.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.

### 2026-06-04 — Chief Advisory Coach added

- Commit `49ede794ad1de0cd2a16ae487fb28ace103913b0` — added Chief Advisory Coach synthesis to `decision_audit_consolidation.py`.
- Commit `51a9cd2f6912af04a65650157c89757dde594a25` — documented Chief Advisory Coach in handoff.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: preserved.

### Earlier important commits

- `a83a88f924694ac74a43ab971c3081557e82258c` — productization roadmap.
- `929d4b27c1e70cd78f8d0c3e80f133ddd3482911` — proactive recommendation preference.
- `8fd184368b1bcc40cc9d174f3eb6bac327b1c2ca` — internal advisory coaches.
- `a4097743652ecf657b60709b653663a8c57b3d97` — ML counts in one-test output.
- `0d30626f040d3fadc5f1d9db09335ee6130d289d` — ML counts in decision audit.
- `2322947c4c8bf25d2d60d4ef899bb1d250b04062` — post-harvest redeployment hardening.

## Current upgrade plan

1. Keep ML shadow-only.
2. Continue collecting execution outcomes until at least `150` execution rows.
3. Continue expanding true regime coverage from `2` to at least `3` regimes.
4. Monitor `state_diagnostic.size_bytes` in `/paper/self-check`; state-size retention is working, so no more compaction changes are needed unless growth resumes.
5. If repeated ticker SSL failures persist, add a data-fetch retry/backoff and warning aggregation layer.
6. Preserve productization path for later dashboard/demo/reporting, but keep current priority on trading quality, telemetry, validation, and state stability.

## Do not do yet

- Do not let ML control trades.
- Do not lower post-harvest thresholds just because cash is high.
- Do not loosen final-close protection.
- Do not bypass self-defense or risk controls.
- Do not require multiple routine test links.
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
6. Proactively recommend high-value, low-risk updates when they improve observability, safety, readiness, continuity, state stability, or productization without changing trading authority.
7. Preserve the productization roadmap: first commercial version should be analytics/paper/dashboard/reporting, not live multi-user brokerage automation.

Current direction:
- ML remains shadow-only.
- Post-harvest redeployment is active.
- Decision audit is included in /paper/self-check.
- ML shadow counts are surfaced in /paper/self-check.
- Internal advisory coaches and Chief Advisory Coach are included in decision_audit_next_actions.
- MAE/MFE telemetry integration and formal walk-forward validation are upgraded.
- ML feature-journal quality and regime tagging are advisory-only readiness/diagnostic layers.
- State-size watchdog has conservative retention/compaction policy and latest EOD self-check confirms state size dropped to 14,499,209 bytes.
- DDOG/ARM SSL download errors appeared in runtime logs but self-check passed; treat as transient data-feed warnings unless persistent.
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
