# Regime-Adaptive Participation and Performance Audit V2

Date: 2026-08-03

## Objective

Restore meaningful paper-account participation without returning to unrestricted
risk. The implementation separates two responsibilities:

1. `paper_regime_adaptive_policy.py` is the paper-only runtime configuration
   owner for participation capacity and sizing ceilings.
2. `performance_audit_lab_v2.py` is advisory research only and evaluates the
   policy with stronger historical methodology.

## Runtime participation policy

`paper_regime_adaptive_policy.py` does not wrap any entry function and does not
place orders. It harmonizes a whitelist of existing constants in:

- `core_entry_pipeline`
- `risk_on_starter_participation_valve`
- `neutral_momentum_starter_extension`
- `paper_underdeployment_repair`
- `paper_participation_allocator`
- `risk_reward_structure`
- selected broad app capacity fields

The policy restores:

- up to four positions in constructive/risk-on conditions;
- up to three new entries per day and two per cycle in favorable conditions;
- 42% target deployment in neutral conditions;
- 52%–62% target deployment in constructive/risk-on conditions;
- final starter targets of 13% neutral, 15% constructive, and 16% risk-on;
- a regime-scaled risk/reward account-risk ceiling of 0.4%–1.2%;
- removal of duplicate 0.18/0.30 sizing multipliers on starter/valve paths.

The policy preserves:

- live-trading authority separation;
- the primary app entry-score floors;
- daily-loss and drawdown halts;
- self-defense;
- cooldowns;
- stop-loss and RR construction;
- sector/bucket controls;
- the absolute 2% per-trade risk ceiling.

Routes:

- `/paper/regime-adaptive-policy-status`
- `/paper/regime-adaptive-policy-apply`

## Performance Audit V2

`performance_audit_lab_v2.py` adds:

- next-session-open execution instead of same-close entries;
- full rolling 252-day train / 63-day test coverage without a four-fold cap;
- static current, static balanced, permissive, and adaptive-balanced profiles;
- strong-risk-on, risk-on, constructive, neutral, defensive, and risk-off
  segmentation;
- defensive/inverse ETF sleeves during deteriorating regimes;
- calendar-year and regime-level metrics;
- symbol-history coverage reporting;
- one-variable ablations for:
  - 2/3/4/6 positions
  - 3/5 confirmations
  - MA50 on/off
  - 12%/16%/18% allocation
  - 7/10/12-day holds
  - 1.2%/1.5%/1.8% stops
- survivorship/selection-bias warnings;
- a forward-shadow confirmation gate before any automated strategy promotion.

Routes:

- `/paper/performance-audit-v2-status`
- `/paper/performance-backtest-v2`
- `/paper/performance-ablation-v2`
- `/paper/performance-regime-report-v2`

Recommended forced test:

```text
/paper/performance-backtest-v2?period=5y&symbols=45&ablation=true&force=true
```

## Deployment

`gunicorn.conf.py` loads the central policy before refreshing the original
restriction audit, then registers V2 research routes. The existing composition
guard remains in place.

`.github/workflows/performance-audit-validation.yml` compiles both new modules
and the full activation stack on relevant pushes.

## Interpretation rules

Do not promote a configuration based on full-sample CAGR alone. Prefer:

- full-history rolling out-of-sample pass;
- positive out-of-sample return and Sharpe;
- acceptable worst-fold drawdown;
- consistent calendar-year and regime performance;
- an ablation winner that is not dependent on one extreme setting;
- at least 30 forward candidates and 20 one-day outcomes.

The runtime policy is paper-only, reversible, and deliberately leaves the
primary score floors unchanged until the V2 and forward evidence identify which
quality gates are genuinely additive.
