# Post-Validation Shadow-AI Research Design

Status: Stage 2 provider-neutral client implemented; runtime integration disabled
Issue: #157  
Runtime authority: unchanged; rules remain the sole execution authority

## Purpose

Add a provider-neutral research plane that can challenge rule-engine proposals,
retain source-aware research evidence, learn from canonical completed outcomes,
and measure whether its disagreements would have improved expectancy net of
inference cost. The system is an experiment, not a trading-policy owner.

Stages 1 and 2 change no runtime behavior. They record the reviewed ownership
boundary and implement a provider-neutral, disabled-by-default structured client
that every later runtime stage must satisfy.

## Repository-wide review findings

The review covered the current handoff, all tracked code and tests, deployment
and workflow configuration, ownership/configuration/state contracts, canonical
execution and accounting boundaries, startup composition, runtime diagnostics,
and the existing research/ML/shadow surfaces. Full repository validation parsed
301 Python files with no compile or static-contract errors. Railway deployment
configuration validation passed.

The existing system already provides most of the evidence substrate:

- `run_report_guard.py` owns the current `run_cycle` observation boundary.
- `runtime_shadow_capture.py` records same-cycle decision parity without adding
  an independent trading policy or callable owner.
- `shadow_decision_comparison.py` and its contract define stable comparison
  identities and score/size parity dimensions.
- `ml_vs_rules_shadow_log.py` and
  `ml_recommendation_counterfactual_ledger.py` already model shadow decisions,
  later outcomes, and training rows.
- `intratrade_path_capture.py`, `mae_mfe_integration.py`,
  `trade_quality_telemetry.py`, and `strategy_scorecard.py` provide canonical
  outcome and path-quality features.
- `research_advisory_engine.py` and `news_sentiment_engine.py` already establish
  advisory-only structured market/fundamental inputs.
- `multi_asset_shadow_ranker.py` proves a research-only module can remain
  disconnected from execution candidates.
- canonical execution IDs and the v4 accounting epoch provide immutable outcome
  identity. The AI layer must consume that evidence read-only.

The startup architecture is intentionally conservative but overlay-heavy.
Later stages must not add another `run_cycle` wrapper, import-time provider call,
import-time worker thread, state-persistence owner, execution route, or order
callable. A request may be enqueued from the existing observer owner only after
the rule decision is complete.

## Authority boundary

The research plane may:

- receive an immutable copy of an already-computed rule proposal;
- retrieve bounded, source-aware research data;
- return `agree`, `reject`, or `unavailable` as a shadow opinion;
- record confidence, risk factors, citations, validation failures, latency,
  tokens, cache usage, and exact configured inference cost;
- join completed shadow records to canonical outcomes by immutable execution ID;
- report counterfactual agreement, disagreement, MFE, MAE, return, and
  incremental expectancy net of inference cost.

It may never:

- approve, reject, delay, trigger, cancel, resize, reprice, or route an order;
- change candidate allowance, selection, ranking, score, size, stop, target,
  exit, exposure, capital allocation, strategy, threshold, or hard-risk state;
- replace or wrap `run_cycle` or any execution/risk/accounting callable;
- write, relabel, repair, reorder, or infer canonical execution rows;
- rewrite portfolio, accounting, history, day-peak, halt, validation, or
  recovery evidence;
- enable live trading or ML/AI execution authority.

Any future proposal to cross that boundary is a new behavior change requiring
separate user authorization and the full validation policy. No amount of shadow
performance evidence promotes authority automatically.

## Planned data flow

1. The existing rules engine finishes its normal decision and produces the
   authoritative proposal/result.
2. `run_report_guard.py`, as the existing observer owner, creates a bounded,
   immutable research request. Enqueueing must be nonblocking and must not alter
   the returned trading result.
3. A single explicitly started research worker consumes the bounded queue after
   runtime composition is complete. Queue saturation drops the new research
   request with telemetry; it never stalls the execution cycle.
4. The provider-neutral client obtains deterministic structured inputs first,
   optionally retrieves allowlisted external sources, and treats every retrieved
   byte as untrusted data rather than instructions.
5. Strict schema validation accepts only `agree`, `reject`, or `unavailable`.
   Timeout, malformed JSON, missing fields, unsafe citations, rate limits, and
   internal errors produce the pessimistic `unavailable` fallback.
6. A bounded shadow record is persisted only through the existing state owner or
   a separately contracted atomic research ledger. Raw prompts, secrets, and
   full retrieved pages are never persisted.
7. After a canonical lifecycle closes, outcome reflection joins by exact
   execution ID and reads strategy/setup/regime/sector/bucket/volatility/signal,
   MFE, MAE, return, and cost evidence without mutating the canonical ledger.
8. Read-only scorecards measure agreement/disagreement quality and incremental
   expectancy net of inference cost. They do not emit execution inputs.

## Failure and threat model

### Provider or schema failure

Research failure returns `unavailable`, records a reason code, and leaves the
rules result untouched. Retries are bounded. Missing provider configuration
means disabled research, not failed trading runtime.

### Prompt injection and manipulated sources

External pages, news, filings, and social content are untrusted evidence. The
client must isolate retrieved content from system instructions, reject embedded
tool or policy directives, allowlist source schemes, normalize citations, hash
stored evidence, and store no executable content. A citation proves provenance,
not truth; conflicting claims remain explicit risk factors.

### Stale or mismatched results

Every request carries schema version, cycle ID, input fingerprint, candidate ID,
and rule-decision timestamp. A result that misses its deadline or does not match
all identities is retained only as invalid telemetry and cannot be joined to a
different cycle or execution.

### Latency, queue pressure, and cost explosion

Provider calls never occur on the execution thread. Queue size, per-cycle
requests, attempts, provider timeout, daily calls, and configured daily cost are
bounded. When a bound is reached, new research work is dropped or disabled with
telemetry; trading continues normally.

### State growth and recovery

Request/result histories are bounded. Large raw source bodies, full prompts,
model reasoning text, and secrets are excluded. Canonical outcome memory is a
read-only derived index and can be rebuilt from immutable execution evidence.

## Structured request and result

The request contract includes:

- schema/cycle/candidate/input identities;
- rule decision and timestamp;
- symbol, side, strategy, setup, regime, sector, bucket, and volatility state;
- proposed entry/stop/target/size as read-only context;
- deterministic signal and risk features;
- source policy and deadline.

The result contract includes:

- `agree`, `reject`, or `unavailable`;
- calibrated confidence and bounded risk-factor codes;
- normalized citations with access time and content hash;
- fallback and validation reason codes;
- provider/model identity and latency;
- prompt, completion, reasoning, and cached-token counts when supplied;
- exact configured USD cost or `null` when exact pricing is unavailable.

Free-form model text is optional, bounded, advisory, and never parsed as an
execution instruction.

## Canonical outcome memory

Outcome memory is keyed first by immutable execution ID, never by a reconstructed
symbol-only trade. Comparable outcomes may be selected using:

- strategy and setup family;
- side and regime;
- sector and allocation bucket;
- volatility state;
- deterministic signal characteristics;
- holding-period and session characteristics.

Every derived row records the canonical source IDs and derivation version.
Missing or contradictory canonical evidence fails the join closed. Historical
rows are not rewritten to make a model appear correct.

## Counterfactual evaluation

Initial evaluation asks only whether the shadow opinion was useful:

- rules entered and AI agreed;
- rules entered and AI rejected;
- research unavailable;
- eventual MFE, MAE, realized return, and exit reason;
- hypothetical reject/agree correctness under a declared metric;
- incremental expectancy and profit factor by sample/confidence bucket;
- inference expense and net incremental expectancy;
- results by strategy, setup, regime, sector, volatility, and calendar segment.

No scorecard can promote itself. Small or concentrated samples remain explicitly
inconclusive.

## Bounded implementation stages

### Stage 1 — design and contract

This document, `shadow_ai_research_contract.json`, and invariant tests. No
runtime code or configuration.

### Stage 2 — provider-neutral client

Strict schemas, typed disabled-by-default configuration, timeouts, bounded
retries, pessimistic fallbacks, citation normalization, untrusted-source
controls, and cost telemetry. Unit tests use deterministic fake providers.

Implemented in `shadow_ai_research_client.py` without a bundled network
transport, provider SDK, route, worker, persistence owner, import-time action, or
runtime registration. The injected provider callable receives the configured
timeout; only explicitly transient transport failures are retried, and the
client independently rejects elapsed-time or request-deadline violations.
Malformed output, identity mismatch, unsafe citations, invalid telemetry, and
missing configuration all produce a complete `unavailable` result. Exact USD
cost remains `null` unless configured per-token-category pricing is sufficient.

### Stage 3 — asynchronous adversarial reviewer

Bounded nonblocking queue, one explicitly started research worker, immutable
request snapshots from the existing observer owner, stale-result rejection, and
no execution-thread provider calls.

### Stage 4 — canonical outcome memory and scorecards

Read-only canonical joins, comparable-outcome retrieval, AI-vs-rules lifecycle
labels, MFE/MAE/return evidence, and net-of-cost counterfactual scorecards.

### Stage 5 — observability and forward evidence

Read-only status/audit surfaces, source/cost/fallback telemetry, state-size and
restart checks, settled Splendid acceptance, and a forward shadow evidence
period. Any later authority discussion remains a separately authorized project.

## Validation requirements

Every runtime stage requires focused unit/integration tests, repository and
Railway validation, exact Gunicorn/bootstrap smoke, and the exact-head Change
Safety, Repository Safety/Performance, Architecture Debt, and full
Refactor/Ownership/Configuration/State/Decision/Runtime/Startup/Research gates.
Runtime stages additionally require settled Splendid self-check and at least one
successful automatic paper cycle. No backtest is required while the system is
strictly telemetry-only; any behavior change requires the full
`VALIDATION_POLICY.md` evidence stack.
