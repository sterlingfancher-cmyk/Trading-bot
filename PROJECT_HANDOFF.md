# Automated Trading Project Handoff — Updated July 21, 2026

## Standing Rule

Every code/configuration update must update this file in the same work session with files changed, versions, commits, routes, safety impact, validation status, and next action.

## Repository and Deployment

- Repository: `sterlingfancher-cmyk/Trading-bot`
- Railway base URL: `https://trading-bot-clean.up.railway.app`
- Routine daily test: `https://trading-bot-clean.up.railway.app/paper/self-check`
- Full diagnostics: `https://trading-bot-clean.up.railway.app/paper/full-self-check`
- Operating mode: paper only
- Live trade authority: none
- ML live authority: none
- Strict stronger-authority benchmark: 150 execution rows and 100 observed outcomes

## Latest Validated Runtime Evidence — July 21, 2026, 19:07:46

The compact self-check passed with no warnings:

- `overall: pass`
- `status: ok`
- `health.warnings: []`
- `terminal_compaction_applied: true`
- `source_contracts_normalized: true`
- `cycle_aware_scanner_comparison: true`
- `runtime_reliability_overlay_version: runtime-reliability-overlay-2026-07-21-v2-entry-contract`

Account and performance snapshot:

- cash: 10111.46
- equity: 10864.08
- positions: DELL and QQQ
- execution rows: 83
- realized total: +733.97
- unrealized PnL: +131.58
- wins/losses: 34/16

Risk snapshot:

- self-defense inactive
- daily loss: 0.0%
- intraday drawdown: 0.047%
- feedback loop clear

Entry-pipeline structure:

- `stack_stable: true`
- `recursion_safe: true`
- `direct_core_base: true`
- `participation_valve_chain_cycle_free: true`
- current callable: `entry_pipeline_xray.wrapped`
- inner callable: `entry_pipeline_composition_guard.composed`

The duplicate-reason TypeError remains historical at July 20, 12:01:39 CDT. Scanner count comparison remains correctly non-assertive without shared cycle identity: decision 54, blocker audit 42, difference 12, `same_cycle_comparison: false`, `source_mismatch: null`.

## Current Core Reliability Versions

- Daily serializer: `daily-self-check-compactor-2026-07-21-v4-source-contracts`
- State transaction manager: `state-transaction-manager-2026-07-21-v1`
- Entry ownership guard: `entry-pipeline-ownership-guard-2026-07-21-v2-read-only-inspection`
- Runtime reliability overlay: `runtime-reliability-overlay-2026-07-21-v2-entry-contract`

The runtime framework is stable. Broad reliability patching is paused unless a concrete failure or measurable operational need appears.

## Active Workstream — Scanner v2

### Milestone 1: expanded shadow universe

Version:

`scanner-v2-shadow-universe-2026-07-21-v1`

A new advisory-only module defines a broader candidate taxonomy across:

- robotics and automation;
- defense and aerospace;
- energy leaders;
- precious metals;
- healthcare leaders;
- quantum computing;
- broad liquid indexes and sector ETFs.

The module compares the expanded shadow set against the current executable universe and reports:

- basket counts;
- total shadow symbols;
- current-universe overlap;
- new shadow candidates;
- authority and mutation assertions.

Route:

`/paper/scanner-v2-shadow-universe-status`

The route is registered as an optional governance endpoint in `one_link_check` through `usercustomize.py`.

### Safety boundary

Milestone 1 is strictly observational:

- `core.UNIVERSE` is not mutated;
- `scan_signals` is not patched;
- no order can be placed by this module;
- no threshold is lowered;
- no sizing or risk limit changes;
- no ML authority changes;
- no live authority changes.

The initial direct executable-universe expansion was not applied. The safe implementation sequence is to gather shadow availability, liquidity, overlap, and eventual outcome evidence before proposing any candidate promotion into the executable universe.

### Files changed

- `scanner_v2_shadow_universe.py`
- `usercustomize.py`
- `PROJECT_HANDOFF.md`

### Commits

- `227ac0d4d559e0aff1140456b48bbc54ad6fd36b` — add advisory-only Scanner v2 shadow universe.
- `78c239dd97f0f2a32f39ee46660ff9c6a0ea9c77` — register the shadow route and optional self-check endpoint.
- Handoff commit: the commit updating this file.

## Scanner v2 Next Steps

Proceed in this order:

1. Validate the new route after Railway redeploys.
2. Add shadow data-quality and liquidity evaluation using the existing provider interfaces, without altering the executable universe.
3. Add composite opportunity-score attribution in shadow mode so each candidate exposes trend, relative strength, volume, momentum, market alignment, and risk components.
4. Add regime-aware shadow weighting and compare rankings across bull, bear, and sideways conditions.
5. Record candidate-to-entry and candidate-to-outcome attribution against the current rule engine.
6. Only after evidence supports improvement, prepare a separately reviewed paper-only promotion gate for selected shadow candidates.
7. Add crypto candidates later as a separate provider and volatility-handling milestone; BTC, ETH, and SOL must not be forced through equity-only data assumptions.

## Remaining Project Priorities

### Shared cycle identity

Propagate one immutable `cycle_id` through scanner output, decision audit, blocked-entry audit, X-Ray, entries, rotations, and post-harvest. This remains the next observability priority after the initial Scanner v2 shadow instrumentation is stable.

### Phase 3A ML advisory evaluation

Continue ML in advisory-only paper mode. Rule thresholds and hard risk controls remain authoritative. Log ML-versus-rules disagreement and subsequent outcomes; no greater ML authority should be considered before the evidence benchmark is met and repeatable improvement is demonstrated.

### Evidence accumulation

Current evidence is 83 execution rows. Before considering live or stronger ML authority:

- reach at least 150 execution rows;
- reach at least 100 observed outcomes;
- validate across multiple market regimes;
- confirm acceptable drawdown and loss clustering;
- retain paper-only operation until a separate explicit approval decision.

## Safety / Authority Policy

All work must preserve:

- internal risk checks;
- existing sizing limits;
- cooldowns;
- self-defense and drawdown halts;
- regime, trend, volume, relative-edge, extension, quality, and futures-bias gates;
- paper-only broker authority;
- no ML execution authority;
- no automatic promotion to live trading.

## Validation Procedure

After Railway redeploys, run:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Confirm the existing baseline remains:

- `overall: pass`;
- `status: ok`;
- `health.warnings: []`;
- stable entry-pipeline fields remain true;
- no newly timestamped runtime error.

Then inspect the new non-mutating route:

`https://trading-bot-clean.up.railway.app/paper/scanner-v2-shadow-universe-status`

Expected fields:

- `status: ok`;
- `overall: pass`;
- `version: scanner-v2-shadow-universe-2026-07-21-v1`;
- `mode: shadow_advisory_only`;
- `core_universe_mutated: false`;
- `scan_signals_patched: false`;
- positive `shadow_symbol_count`;
- populated overlap and new-shadow-candidate counts.

Use `/paper/full-self-check` only for fail, missing critical fields, or a newly timestamped runtime error. Do not run mutating repair or execution endpoints during routine validation.
