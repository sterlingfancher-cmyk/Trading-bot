# Trading Bot System-Wide Architecture Audit — July 21, 2026

## Scope

Static review of the current default branch, including:

- latest terminal self-check commits and deployed runtime evidence;
- startup/runtime module registration and watchdog behavior;
- entry-pipeline ownership, composition, X-Ray, and sanitizer layers;
- state loading, saving, backup, and run-cycle locking;
- scanner, decision-audit, blocker-audit, and post-harvest telemetry;
- risk/self-defense reporting and authority boundaries;
- ML Phase 3A readiness and authority gates;
- repository-wide search for state writers and public entry-callable modifiers.

This audit is broader than a single endpoint review, but it is not a formal proof of every execution path. Dynamic concurrency and broker-integration testing remain separate work.

## Latest Push Verification

The terminal serializer deployment was structurally complete:

- commits `06e0bc313f1be33502105707676f1fe90371c269`, `06a6ba1392e3214aea5bcb52ec98667b82125cc0`, and `3469935a7686bf8e9bc9bbbca61c7853734c347f` exist on the default branch;
- runtime returned `terminal_compaction_applied: true`;
- verbose summary objects no longer leaked into `/paper/self-check`;
- account, positions, PnL, risk, and starter-valve fields were populated.

The source-normalization portion was not functionally complete. Persisted X-Ray telemetry stores composition under `composition`, while the serializer expected `composition_status`. Native decision audit nests scanner metrics under `latest_cycle`, and ML readiness can originate from the Phase 3A gate rather than flattened decision-audit summaries. This caused false `warn` output and null compact fields.

Repair commit:

- `cd5cce24c77c840405914f3cc18e8b762ca09c54`
- version `daily-self-check-compactor-2026-07-21-v4-source-contracts`

The repair normalizes those source contracts and supports status producers that require either zero arguments or the core runtime module.

## Executive Assessment

The trading controls appear materially safer than the reporting architecture. The current account, risk, entry-stack, and live-authority evidence is healthy, but the codebase has accumulated a large number of runtime monkeypatches and independent load-modify-save writers. The highest forward risk is not an obvious threshold defect; it is ownership drift or lost state updates between otherwise valid modules.

### Current risk rating

- Trading/risk authority: **low-to-moderate risk**
- State consistency: **high engineering risk**
- Runtime wrapper ownership: **moderate-to-high engineering risk**
- Telemetry consistency: **moderate engineering risk**
- ML live-authority leakage: **low observed risk**
- Diagnostic reliability: **moderate engineering risk**

## Findings

### P0 — State updates are atomic but not transactional

`state_io_hardening.py` makes each individual write atomic and applies a save lock. That prevents partial JSON files, but it does not protect the full read-modify-write transaction used throughout the repository.

Typical pattern:

1. Module A loads state.
2. Module B loads the same state.
3. Module A modifies one subtree and saves.
4. Module B modifies a different subtree and saves its older whole-state copy.
5. Module A's update can be silently lost.

Repository search found many independent `save_state` callers, including entry-pipeline telemetry, ML modules, risk modules, journal modules, volatility modules, and strategy diagnostics.

**Impact:** counters can move backward, audit fields can disappear, execution rows can regress, and current account/risk information can be replaced by a stale snapshot.

**Required remediation:** introduce one authoritative transaction API such as `update_state(mutator, expected_revision=None)` that locks before loading, increments a monotonic revision, applies the mutation, validates invariants, and writes while still holding the same lock. Migrate direct load-modify-save writers incrementally.

### P0 — Runtime watchdog repeatedly invokes state-writing ownership guards

`usercustomize.py` runs a 1,200-iteration watchdog at 0.1-second intervals. During each pass it reapplies multiple runtime modules and calls the entry-pipeline ownership guard. The ownership guard loads and saves state on every enforcement, even when no drift exists.

**Impact:** heavy startup write amplification, enlarged lost-update window, unnecessary filesystem activity, and a higher chance that diagnostic state overwrites a concurrent trading-cycle update.

**Required remediation:** make ownership checks read-only when the stack is already owned; persist only on drift, repair, error, or a low-frequency heartbeat. Replace the 0.1-second polling loop with event-driven installation plus a much slower integrity check.

### P0 — Some status/read paths have runtime side effects

Examples:

- Entry Pipeline X-Ray `status_payload()` calls its patch function.
- Composition and ownership status functions can enforce or rebuild wrappers.
- Several registration/status flows persist telemetry while answering diagnostics.

**Impact:** a routine GET request can change callable ownership or write state. This weakens the rule that `/paper/self-check` is validation-only and makes testing capable of masking startup drift by repairing it during observation.

**Required remediation:** separate every module into explicit `inspect()` and `repair()` functions. Status endpoints must call only `inspect()`. Startup may call `install()`; intentional repair endpoints may call `repair()`.

### P1 — State authority is split between disk and `core.portfolio`

Different modules prefer different sources:

- some call `load_state()` first;
- some prefer `core.portfolio` first;
- some fall back silently between them;
- decision audit reads `core.portfolio` directly;
- ML Phase 3A gate also prefers `core.portfolio` before disk.

**Impact:** two modules can produce internally valid but different answers at the same timestamp. This explains some account, ML, and scanner telemetry discrepancies.

**Required remediation:** define one authoritative state snapshot provider with revision and timestamp metadata. All diagnostics should consume the same immutable snapshot per request or per cycle.

### P1 — Scanner telemetry lacks a shared cycle identity

Decision audit, blocker audit, scanner state, X-Ray meaningful-cycle telemetry, and post-harvest telemetry can reflect different cycles. Counts such as 54 versus 42 are therefore not necessarily contradictory, but there is no reliable way to prove whether they refer to the same scan.

**Impact:** false mismatch warnings, ambiguous blocker coverage, and difficulty tracing a symbol through scanner → candidate preparation → entry decision.

**Required remediation:** generate a `cycle_id` at the beginning of `run_cycle` and propagate it, with `cycle_started_at` and `source`, into scanner audit, rejected signals, blocker audit, X-Ray, entries, rotations, and post-harvest state. Compare counts only when cycle IDs match.

### P1 — Broad exception suppression obscures ownership and persistence failures

Many modules use `except Exception: pass` around patching, persistence, registration, and diagnostics.

**Impact:** the system can appear healthy while a repair, state write, or route installation silently failed. Missing fields then surface later as reporting defects rather than actionable root-cause errors.

**Required remediation:** retain fail-safe behavior but record bounded structured errors in one diagnostics ring buffer with module, operation, exception type, timestamp, and cycle/state revision.

### P1 — Wrapper architecture remains highly coupled

The current entry path is deliberately composed and guarded, but several historical modules still contain public-callable patch logic. Ownership guard disables one known legacy patch, while usercustomize repeatedly reasserts the intended order.

**Impact:** adding or reordering a module can displace the public callable, create nested wrappers, or change telemetry without changing core logic.

**Required remediation:** replace runtime monkeypatch ownership with a single declarative pipeline builder. Each layer should be a registered stage in a fixed list, and only the builder should assign `app.try_entries_and_rotations`.

### P1 — Diagnostic persistence writes the entire trading state

Entry X-Ray, ownership guard, ML gates, and other diagnostics append their telemetry by loading and saving the complete state object.

**Impact:** non-critical diagnostics participate in the same whole-state overwrite risk as orders, positions, and performance.

**Required remediation:** either move diagnostic telemetry to a separate file/store or route it through the transactional state API with isolated subtree updates.

### P2 — Read-side state hardening does not consistently use the hardening lock

`hardened_load_state()` first calls the original loader and only uses `safe_load_json_file()` after an exception. If the original loader is not itself locked, the advertised read locking is not universally applied.

**Impact:** lower than the lost-update problem because atomic replace protects JSON integrity, but readers may bypass retry/backup behavior and return inconsistent source choices.

**Required remediation:** have hardened load call the locked reader directly, then apply any original normalization to that snapshot rather than calling the original file reader first.

### P2 — ML readiness reporting is inferred in multiple ways

Phase 3A readiness appears in:

- `ml_phase3a_early_paper_gate`;
- `ml_phase25` persisted state;
- decision-audit ML shadow;
- text inside `next_actions`;
- compact self-check reporting.

Live authority is consistently disabled in reviewed code, which is positive. However, multiple readiness derivations can disagree.

**Required remediation:** make the Phase 3A gate status the sole readiness source and let all other modules reference its structured fields. Do not infer readiness from recommendation text.

### P2 — Health semantics mixed reporting completeness with engine health

The compact route previously changed overall health to `warn` when advisory fields were missing even though account, risk, and trading controls were healthy.

**Impact:** operator alert fatigue and difficulty distinguishing engine safety from diagnostic completeness.

**Required remediation:** preserve separate fields such as `engine_health`, `diagnostic_health`, and `telemetry_consistency`. The v4 source-contract repair reduces false warnings, but semantic separation remains recommended.

## Positive Controls Confirmed

- Atomic replace, fsync, backups, and a non-overlapping run-cycle lock exist.
- Entry Pipeline X-Ray is diagnostic-only and rethrows runtime errors rather than hiding them.
- Composition/ownership metadata clearly identifies the intended callable chain.
- Risk-on starter valve declares and preserves cooldown, halt, and self-defense authority.
- ML Phase 3A gate explicitly denies live, execution, sizing, and risk-control authority.
- Terminal daily serializer uses a new allowlisted dictionary rather than mutating or merging verbose payloads.
- Full diagnostics remain separate from the routine daily route.

## Remediation Order

1. Build transactional state mutation with revision checks.
2. Stop watchdog write amplification and make stable ownership checks read-only.
3. Separate inspect/install/repair behavior for all runtime modules.
4. Add cycle IDs and state revision IDs across scanner and entry telemetry.
5. Move diagnostic telemetry away from whole-state writes.
6. Consolidate state authority and ML readiness authority.
7. Replace public monkeypatch accumulation with one declarative entry-pipeline builder.
8. Add static and runtime contract tests for the daily serializer.

## Proposed Validation Tests

### State concurrency

- Run two concurrent subtree updates and verify neither is lost.
- Reject a save based on an older revision unless explicitly merged.
- Verify account, positions, and execution rows never regress without a documented reconciliation event.

### Entry ownership

- Install every runtime module in multiple orders.
- Confirm exactly one X-Ray outer wrapper and one composition-owned inner callable.
- Confirm status GET requests do not alter callable identity or state revision.

### Scanner traceability

- Verify one cycle ID across scanner, blockers, X-Ray, post-harvest, entries, and rotations.
- Treat count differences as warnings only when cycle IDs match.

### Authority

- Assert no ML module can place trades, size positions, change risk controls, or enable live mode.
- Assert self-defense, cooldown, halt, and daily-loss controls remain authoritative under every starter/redeployment path.

### Daily serializer

- Fixture tests for native module payloads, persisted-state payloads, missing optional diagnostics, and historical errors.
- Assert the exact top-level allowlist and absence of verbose keys.
- Assert reporting-only requests do not change state revision.

## Immediate Next Validation

After Railway redeploys commit `cd5cce24c77c840405914f3cc18e8b762ca09c54`, use only:

`https://trading-bot-clean.up.railway.app/paper/self-check`

Expected markers:

- `version: daily-self-check-compactor-2026-07-21-v4-source-contracts`
- `terminal_compaction_applied: true`
- `source_contracts_normalized: true`
- populated entry-pipeline status/stability/callables;
- populated ML advisory/readiness fields;
- no `compact_source_fields_missing` warning when source modules are available.

A scanner source mismatch may remain until shared cycle IDs are implemented. It should not by itself change engine health.