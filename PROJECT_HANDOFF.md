# Automated Trading Bot Project Handoff

Last updated: 2026-06-04

Continuity source for future chats. New sessions should read this file, inspect recent commits, preserve the one-test workflow, and continue without asking the operator to reconstruct prior work.

## Repository and routine test

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Main app file: `app.py`
- Startup file: `wsgi.py`
- Persistent state: `/data/state.json`
- Routine test link: `https://trading-bot-clean.up.railway.app/paper/self-check`

Routine post-push rule: run only `/paper/self-check`. Extra diagnostic routes are optional and only for debugging.

## Current guardrails

- Preserve one-test workflow.
- Keep ML shadow-only until promotion gates pass and the operator approves.
- Do not lower risk controls or entry-quality discipline without explicit approval.
- Manual `/paper/run` stays protected by `RUN_KEY`.
- Keep this handoff updated after meaningful code changes or test results.

## Latest known status

Most recent self-check before the newest expansion push was 2026-06-04 15:26 CDT:

- Overall: `pass`
- Status: `ok`
- Warnings: `[]`
- Equity: about `$11,001.76`
- Cash: about `$9,672.49`
- Open positions: `3`
- Positions: `DELL`, `QQQ`, `SNDK`
- Realized total: `$857.68`
- Unrealized P&L: about `$144.10`
- Losses today: `0`
- Execution rows: `82 / 150`
- ML rows: `6000`
- Labeled outcome rows: about `1823`
- Observed outcomes: `49`
- Latest predictions: `25`
- Phase 3A ready: `false`
- State size: `14,499,209` bytes after retention, down from about `16.86 MB`

## Active modules

### Missed Mover Audit

File:

- `missed_mover_audit.py`

Routes:

- `/paper/missed-mover-audit?symbol=MNTS`
- `/paper/missed-mover-audit-status`

Purpose:

- Explain why a fast-moving symbol was missed.
- Determine whether a symbol was in the watchlist/universe, open positions, recent trades, scanner/decision sections, candidate symbols, or blocked symbols.
- Classify known speculative/microcap buckets such as space and small-cap momentum.
- Recommend whether the miss looks like a universe gap, rejection/block, or timing/quality-gate issue.

Guardrails:

- Advisory-only.
- Does not trade.
- Does not change risk controls.
- Does not change ML authority.
- Does not lower thresholds.
- Does not change the one-test workflow.

### Paper-only controlled expansion

Files:

- `paper_controlled_expansion.py`
- `wsgi.py`

Expected version:

```text
paper-controlled-expansion-2026-06-04-v1
```

Purpose:

- Paper-only controlled capacity expansion to collect execution observations faster.
- Effective clean-market max positions: `16`.
- Post-harvest target open positions: `8`.
- Post-harvest underdeployment threshold: `6` open positions.
- Max new entries per cycle: `2`.
- Starter allocation factor: `0.45`.
- Max active paper research slots: `2`.
- Adds `paper_learning` metadata to successful entries and positions.
- Research-slot trades are marked as excluded from core strategy score but included in ML observation data.
- ML authority remains `shadow_only`.
- Normal entry quality checks, cooldowns, stop rules, self-defense, and final-close protections still apply.

Optional route:

```text
/paper/paper-controlled-expansion-status
```
### Runtime module registry and expansion impact monitor

Files:

- `runtime_module_registry.py`
- `expansion_impact_monitor.py`
- `wsgi.py`

Purpose:

- Verify important runtime overlays are loaded.
- Confirm optional diagnostic routes are registered.
- Monitor the paper-only controlled expansion after the 14 → 16 max-position change.
- Track execution rows, observed outcomes, open positions versus target, paper-learning tag quality, state-size growth, drawdown, losses, and ML authority.
- Keep both modules advisory-only.

Routes:

- `/paper/runtime-module-registry-status`
- `/paper/startup-patch-status`
- `/paper/expansion-impact-status`
- `/paper/expansion-impact-monitor`

Guardrails:

- No trading authority changed.
- No ML authority changed.
- No risk controls changed.
- No entry thresholds lowered.
- No self-defense/final-close bypass.
- One-test workflow preserved.

### Post-harvest redeployment

Files:

- `post_harvest_redeployment_controller.py`
- `post_harvest_entry_fallback.py`

Purpose: controlled starter redeployment after harvesting, without forcing entries or bypassing normal quality/risk gates. With paper-controlled expansion, target open positions are now `8` and underdeployment threshold is `6`.

### Decision audit and advisory coaches

File: `decision_audit_consolidation.py`

Expected version:

```text
decision-audit-consolidation-2026-06-04-v6-chief-advisory-coach
```

Includes Trade Quality Coach, Risk Coach, Post-Harvest Coach, and Chief Advisory Coach. All are advisory-only.

### ML shadow/readiness stack

Files:

- `ml_phase2_shadow.py`
- `ml_phase25_readiness.py`
- `ml_feature_journal_quality.py`
- `intratrade_path_capture.py`
- `mae_mfe_integration.py`

Status: ML remains shadow-only. Current bottlenecks are execution rows, observed outcomes, regime coverage, MAE/MFE maturity, and formal walk-forward maturity.

### State-size retention

File: `state_size_watchdog.py`

Expected version:

```text
state-size-watchdog-2026-06-04-v2-retention-policy
```

Purpose: cap or thin derived telemetry while preserving trades, positions, cash/equity, risk controls, summaries, and execution history. Latest self-check showed state size reduced to `14,499,209` bytes.

## Optional diagnostic routes

Use only when needed:

```text
/paper/paper-controlled-expansion-status
/paper/state-size-watchdog
/paper/telemetry-retention-status
/paper/ml2-status
/paper/ml-readiness-status
/paper/ml-phase25-status
/paper/ml-feature-journal-status
/paper/regime-tagging-status
/paper/mae-mfe-integration-status
/paper/intratrade-path-status
/paper/decision-audit-status
/paper/no-entry-diagnostic
```

## Update ledger

### 2026-06-04 — Missed Mover Audit added

- Files changed: `missed_mover_audit.py`, `wsgi.py`, `PROJECT_HANDOFF.md`.
- Reason: MNTS made a large move and was not visible in open positions, candidates, or blocked symbols. Add a diagnostic route to distinguish scanner-universe gaps from rejected/blocked/timing issues.
- Route: `/paper/missed-mover-audit?symbol=MNTS`.
- Trading authority changed: no.
- ML authority changed: no.
- Risk controls changed: no.
- Entry thresholds changed: no.
- One-test workflow changed: no.

### 2026-06-04 — Runtime registry and expansion impact monitor added manually

- Files changed: `runtime_module_registry.py`, `expansion_impact_monitor.py`, `wsgi.py`, `PROJECT_HANDOFF.md`.
- Reason: after paper-only controlled expansion, add observability before adding more trading features.
- Runtime registry checks whether critical overlays and optional diagnostic routes are present.
- Expansion impact monitor tracks execution-row growth, observed outcomes, position count versus target, paper-learning tag quality, state-size growth, drawdown, losses, and ML authority after the expansion.
- Trading authority changed: no.
- ML authority changed: no; ML remains shadow-only.
- Risk controls changed: no.
- One-test workflow changed: no.
- Next step: run only `/paper/self-check` after Railway redeploy.

### 2026-06-04 — Paper-only controlled expansion added

- Commit `a1f983daec8118f9eb8e9d12ca8ddb235f66d5e3` — created `paper_controlled_expansion.py`.
- Commit `1006ae94523019831470ab047e7691f67fdd792c` — wired the module into `wsgi.py` and added optional route registration.
- Files changed: `paper_controlled_expansion.py`, `wsgi.py`, `PROJECT_HANDOFF.md`.
- Reason: operator wanted slightly more paper-mode aggressiveness to scale execution observations faster.
- Capacity changed: clean paper-mode max positions to `16`; post-harvest target to `8`; max entries/cycle remains `2`; starter allocation `0.45`.
- ML authority changed: no.
- Risk controls changed: no.
- One-test workflow changed: no.
- Next step: run `/paper/self-check` after Railway redeploy and verify clean pass.

### 2026-06-04 — End-of-day self-check passed after state-size retention

- Commit `437204508a4a85fd5ada07c1f46c1f138b8b84e7` — logged successful EOD self-check.
- Result: `overall: pass`, `status: ok`, `warnings: []`; state size dropped to `14,499,209` bytes.

### 2026-06-04 — Conservative state-size retention policy added

- Commit `501f47566495e5e4e08c72b9c62cb74ebb9ca09a` — retention policy in `state_size_watchdog.py`.
- Commit `7f50badf70baca8b6d7a27a92bd234cdfd6d0b7a` — handoff update.

### 2026-06-04 — Feature journal quality and regime tagging added

- Commit `726dd35bb9a6b9bf8b0d3ce43f45a978845b4403` — created `ml_feature_journal_quality.py`.
- Commit `df2ee8e3938e0323028d548200c8f33c2a98cdb6` — hardened enrichment after ML2 row refresh.
- Commit `cfb151b244fe093a933ce45e2e1229d0e1424abe` — wired diagnostics.

### 2026-06-04 — MAE/MFE telemetry and formal walk-forward validation upgraded

- Commit `00b25cb8f8927ff545f29821c2430e56b9c80e95` — readiness validation.
- Commit `f405c2a0582e779a9722fcf73b131632b3c3db2a` — MAE/MFE bridge.

### 2026-06-04 — Chief Advisory Coach added

- Commit `49ede794ad1de0cd2a16ae487fb28ace103913b0` — Chief Advisory Coach.
- Commit `51a9cd2f6912af04a65650157c89757dde594a25` — handoff update.

## Current upgrade plan

1. Run `/paper/self-check` after the paper-controlled expansion push.
2. Confirm `overall: pass`, `status: ok`, and `warnings: []`.
3. Keep ML shadow-only.
4. Continue collecting execution outcomes toward `150` execution rows.
5. Monitor drawdown, state size, and whether execution rows increase faster.
6. Add data-fetch retry/backoff only if ticker SSL failures persist.

## New-chat startup prompt

```text
Please continue my automated trading bot project.

Repo: sterlingfancher-cmyk/Trading-bot
Railway base URL: https://trading-bot-clean.up.railway.app
Routine test rule: only use /paper/self-check after normal pushes.

Before making changes:
1. Review PROJECT_HANDOFF.md.
2. Review recent GitHub commits.
3. Preserve the one-test workflow.
4. Keep ML shadow-only unless promotion gates pass and I approve.
5. Do not lower risk controls without explicit approval.
6. Proactively recommend safe observability/readiness/state-stability updates.

Current direction:
- Paper-only controlled expansion is active: max positions 16, target positions 8, max 2 entries/cycle, starter allocation 0.45, research slots max 2.
- ML remains shadow-only.
- Continue collecting execution rows toward 150.
```
