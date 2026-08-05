# Project Handoff — Current Paper-Trading Runtime

Last updated: 2026-08-04 20:38 CDT  
Repository: `sterlingfancher-cmyk/Trading-bot`  
Branch: `main`  
Code head covered by this handoff: `6012f2a9eb4c15a73a9f8991fcb507904aa7df9b`  
Canonical paper service: `https://web-production-e1796.up.railway.app`  
Railway project/service: `splendid-creativity / web`

## Executive Status

The paper bot is deployed, persistent state is now working, the entry bottleneck that prevented a second controlled starter was repaired, machine learning remains shadow-only but now records independent counterfactual recommendations, and the scanner now includes a broad market momentum-discovery prefilter instead of relying primarily on a closed hand-selected ticker list.

The runtime remains paper-only. The rules engine is the sole execution authority. Machine learning cannot place orders, override a rejection, alter sizing, relax risk controls, or obtain live authority.

## Canonical Operating Links

- Routine audit: `/paper/daily-audit`
- Tiny self-check: `/paper/self-check`
- Targeted diagnostics: `/paper/full-self-check`
- Paper state: `/paper/status?full=1`
- Persistence: `/paper/state-persistence-contract-status`
- Cycle completion: `/paper/cycle-completion-contract-status`
- ML Phase 2: `/paper/ml2-status`
- ML recommendation ledger: `/paper/ml-counterfactual-ledger-status`
- ML training dataset: `/paper/ml-counterfactual-training-dataset`
- Broad momentum status: `/paper/broad-momentum-discovery-status`
- Broad momentum candidates: `/paper/broad-momentum-candidates`

## Persistent State — Resolved

A Railway volume is mounted at:

```text
/app/data
```

The application automatically uses Railway's `RAILWAY_VOLUME_MOUNT_PATH`; no custom `STATE_DIR` variable is required for the current deployment.

Latest validated persistence state:

- Persistent mount detected: `true`
- Configured directory: `/app/data`
- State file: `/app/data/state.json`
- State file exists: `true`
- Backup: `/app/data/state.json.bak`
- Backup exists: `true`
- In-memory and on-disk richness matched
- Daily-audit persistence section: `pass`

Important historical limitation: the earlier TSM/HWM paper state that disappeared before the volume was attached cannot be safely reconstructed from the current repository or runtime evidence. Do not claim that state was restored. The present paper account is the authoritative post-reset baseline.

## Latest Validated Paper Account

Capture time: 2026-08-04 20:27:59 CDT

- Cash: `$6,425.12`
- Equity: `$9,988.16`
- Open positions: `4`
- Positions: `MARA`, `AI`, `POWL`, `CRWD`
- Unrealized P&L: `-$11.84`
- Realized P&L: `$0.00`
- Execution rows: `4`
- Risk halted: `false`
- Self-defense active: `false`
- Intraday drawdown: `0.123%`
- Absolute daily-loss ceiling: `3.0%`
- Hard intraday drawdown halt: `2.5%`

The market was closed during the latest post-deployment capture, so the automatic cycle correctly completed as `skipped` with reason `after_regular_session`. The auto-runner remained enabled and healthy.

## Current Effective Participation Limits

Unless a separately validated controlled-expansion state is active, the effective paper controls are:

- Maximum standard starter positions: `4`
- Maximum standard starter entries per day: `3`
- Risk-on starter entries per cycle: `1`
- Normal position target: approximately `12%–18%` of equity
- Current cautious target observed: `11.475%` of equity
- Maximum account risk per trade at the configured stop: `2%`
- Starter cash check: at least `35%` cash before another starter
- Practical post-sizing cash reserve: approximately `30%`
- Practical standard deployment ceiling: approximately `70%`

A paper controlled-expansion layer exists with higher theoretical ceilings, but it activates only under its own favorable-regime and safety conditions. Do not treat its maximums as the normal operating limits.

## Entry-Pipeline Repair Completed

The one-position lock was caused by a combination of timestamp-spacing interpretation, overly sensitive tiny-drawdown gates, and a false chase/pattern veto. The repair preserved the existing daily entry cap, spacing, position cap, sector and bucket diversification, exposure limits, hard risk halts, and sizing controls.

The controlled second-starter tolerance is paper-only and narrowly constrained. It requires a constructive or risk-on market, exactly one existing position, high cash, no realized losses, no active risk halt or self-defense condition, very small account drawdown, and a bounded loss on the first position.

The live result was successful: the account progressed beyond one position without globally lowering the strategy score floor or disabling risk controls.

Key repair commits include:

- `6ec6cb13fde457350465f191562ae5881faf088a` — Repair starter spacing and tiny-drawdown participation gate
- `d152ea0660bf69d2a47bee2b0c3c3626e15dad1b` — Add controlled favorable-regime pattern exception
- `93eec508b55c55343bb635491d932be5c99fab0b` — Add controlled constructive-market second-starter tolerance
- `3f798c55e1a938f6b4be692382a49abade3d225a` — Allow controlled second starter through small unrealized drawdown
- `01dd6812bde1015cd3d8d56ac34fec0535a4d48c` — Load second-starter tolerance from the bootstrap path

## Machine Learning — Current Role

ML remains in `shadow_recommendation_only` mode.

It now independently evaluates scanner candidates and records:

- ML recommendation: enter, avoid, or neutral
- Probability, confidence, edge, and rank
- Rules allow/block decision and exact reason
- Whether the candidate was actually executed
- 15-minute, 60-minute, end-of-day, and next-session outcomes when available
- Maximum favorable and adverse excursion
- Stop-versus-target path when available

The ledger distinguishes:

- Executed outcomes: strongest evidence and full training weight
- Counterfactual outcomes: useful but discounted evidence

Counterfactual rows do not count toward promotion gates. ML still cannot select or execute a blocked trade, alter a rules score, change sizing, relax risk, or place an order.

Key ML commits:

- `276ee79dc3077b54a956ed103f081a7001c5c165` — Add rules-gated ML counterfactual recommendation ledger
- `95ebdaa7da23242bd0ad89f5d27c07156def1672` — Test the ledger
- `e30969bde00f7ccf8598757805a89df0b126a99b` — Start the ledger during guarded bootstrap
- `231f69e8cefc57cb1fef6a57df21f355784ec804` — Load the ledger from the root bootstrap path
- `dac39f322164f9b3bc278652ecb3f46db3c6259c` — Register the ledger in the WSGI runtime

ML promotion remains prohibited until the formal evidence gates pass and the user explicitly approves a change in authority.

## Broad Market Momentum Discovery — Deployed

The scanner no longer depends primarily on a manually maintained ticker universe. A bounded, paper-only discovery layer now screens broad U.S. market momentum and passes the strongest liquid candidates into the existing detailed scanner.

Current discovery sources:

- Market-wide momentum screen
- Day gainers
- Most-active stocks
- Existing positions
- SPY, QQQ, IWM, and DIA
- Original ticker/theme list as fallback coverage

Current liquidity floors:

- Minimum price: `$3.00`
- Minimum daily volume: `350,000`
- Minimum daily dollar volume: `$10,000,000`
- Minimum market capitalization when available: `$100,000,000`

Current bounded limits:

- Maximum discovery candidates retained: `160`
- Maximum broad-momentum slots: `80`
- Maximum original/fallback slots: `25`
- Maximum final working universe: `110`
- Refresh cache: `900 seconds`

Latest forced live discovery validation:

- Raw screen results: `450`
- Unique liquid eligible stocks: `305`
- Selected momentum candidates: `160`
- Provider errors: none
- Discovery duration: approximately `1.57 seconds`

Examples in the validated candidate set included `LIFE`, `PLTR`, `IBTA`, `SOPH`, `DORM`, `W`, `TSAT`, `AMRC`, `PAY`, and `ZBRA`.

The discovery layer only determines which symbols deserve expensive detailed evaluation. The existing scanner, strategy score, entry rules, risk controls, sector limits, sizing, and execution pipeline remain authoritative. Theme baskets are retained primarily as classification and concentration-control containers rather than closed discovery boundaries.

Broad-discovery commits:

- `2270a928f647b91165d02e514637af71321e7dfa` — Add broad market momentum discovery prefilter
- `aed50ebdab29b3a435740c7e61a62408e184371d` — Test broad market momentum discovery
- `4ce3ce806e8dc0d27d4f75ed9557f5fc7dde7ac6` — Register broad discovery in WSGI
- `13be15a36e7d212d682ba4bb8d92120465d093ca` — Register cycle-hook ownership
- `6012f2a9eb4c15a73a9f8991fcb507904aa7df9b` — Declare discovery watchdog units

PR `#7`, **Add broad market momentum discovery prefilter**, was merged into `main`.

## Validation State

Validated as successful:

- Repository safety and performance validation
- Python compilation for new modules
- Focused broad-discovery unit tests
- Exact Gunicorn startup smoke
- Both Railway deployment contexts
- Persistent-state survival through deployment
- Broad momentum status and candidate routes: HTTP 200
- ML ledger status and training-dataset routes: HTTP 200
- Cycle-completion contract: healthy
- Daily operational audit: responsive and bounded

Latest broad-momentum live artifact: `8914892837`  
Latest state-capture workflow run: `30966425023`

The separate refactor/governance audit remains red because the repository still contains legacy ownership and typed-configuration findings. That red status is technical-debt evidence, not proof that the current Railway deployment or the new scanner feature failed. Do not ignore it, but do not misclassify it as a live outage.

## Known Warnings and Technical Debt

1. The daily audit still reports `rejection_count_missing` for scanner telemetry even though signals and blocker rows exist.
2. Trade-journal reconciliation remains incomplete because the summarized journal row counts are not populated alongside the four execution rows and four open positions.
3. The direct `/paper/runtime-shadow-capture-status` route returned HTTP 404 in the latest capture, while the daily audit's in-state runtime-shadow section reported healthy parity. The route registration should be reconciled without changing runtime authority.
4. Broad discovery has been validated after hours, but its first market-open replacement of the executable working universe still needs direct evidence.
5. Legacy architecture ownership and configuration-contract findings remain unresolved.

## Next Priorities

### 1. Validate the first market-open broad-discovery cycle

Confirm:

- The executable working universe contains current momentum leaders rather than only the original base list
- Current positions and benchmark ETFs remain protected
- The detailed scanner receives a bounded 75–110 symbol set
- Cycle duration stays within the provider-timeout and stale-cycle contracts
- Candidate source, promotion, rejection, and selection telemetry are populated
- No recursion or wrapper-chain regression appears

### 2. Close observability gaps

Populate and reconcile:

- Scanner rejection totals
- Trade-journal execution-row count
- Trade-journal open-position count
- Runtime-shadow status route registration

### 3. Evaluate discovery quality, not only discovery breadth

After several market-open cycles, compare:

- Momentum candidates promoted versus rejected
- Rules-approved candidates versus actual outcomes
- Fixed-list candidates versus market-wide discoveries
- Candidate diversity by sector and bucket
- Cycle duration and provider failure rate
- Whether the broader universe improves opportunity quality or merely increases noisy signals

### 4. Mature the ML evidence set

Continue collecting executed and counterfactual labels. Do not grant ML trade authority. The next permissible ML step, only after sufficient out-of-sample evidence, is paper-only ranking among candidates already approved by the rules engine.

### 5. Proactive performance review doctrine

Future work should identify structural bottlenecks before adjusting thresholds. Priority review areas are opportunity discovery, capital efficiency, rejection-cost analysis, regime adaptation, correlation/concentration, exit quality, provider reliability, and evidence quality. Each behavioral change should be isolated on a branch, tested, reviewed for authority changes, and then deployed with live read-only validation.

## Non-Negotiable Safety Boundaries

- Paper trading only
- Rules engine remains execution authority
- ML remains shadow recommendation only
- No restoration claims for missing historical TSM/HWM state
- No bypass of hard risk, drawdown, daily-entry, spacing, position, sector, bucket, or sizing controls
- Never infer a successful deployment solely from a GitHub commit; verify the live Railway service
- Never infer persistence solely from code; verify `/app/data/state.json` and its backup live
- Do not weaken thresholds merely to create more trades; diagnose the actual bottleneck first

## Handoff Instruction for the Next Session

Read this document before modifying the project. Start with the current live state and the latest merged `main`, not an older conversation snapshot. Verify persistent storage, cycle completion, the daily audit, ML authority, and broad-momentum discovery before making behavioral changes. Preserve the user's moderate-to-aggressive risk posture while honoring the 3% maximum daily-loss ceiling, 2% per-trade risk ceiling, and rules-gated paper-only architecture.
