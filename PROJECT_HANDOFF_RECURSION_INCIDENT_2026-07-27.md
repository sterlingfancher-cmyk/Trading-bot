# Scanner Wrapper Recursion Incident — July 27, 2026

## Incident

Railway remained healthy at `/health` and `/paper/status`, but automatic cycles and `/paper/self-check` failed with `maximum recursion depth exceeded while calling a Python object`.

The traceback showed an alternating callable chain between:

- `scanner_v2_candidate_lifecycle_trace.wrapped`
- `shared_cycle_identity.wrapped`

## Root cause

Each module checked only the outermost `scan_signals` callable for its own patch marker. The `usercustomize.py` watchdog repeatedly reapplied both modules. Once one wrapper became outermost, the other module could no longer see its marker and wrapped again. Repetition built an alternating recursive chain.

## Recovery changes

1. `shared_cycle_identity.py`
   - Version: `shared-cycle-identity-2026-07-27-v2-recursion-guard`
   - Adds bounded callable-chain marker inspection.
   - Refuses to add another shared-cycle wrapper when one already exists anywhere in the chain.
   - Commit: `71efd0380364f9d3e5adfa4708b50974ba8789a7`

2. `scanner_v2_candidate_lifecycle_trace.py`
   - Version: `scanner-v2-candidate-lifecycle-trace-2026-07-27-v2-recursion-guard`
   - Adds bounded callable-chain marker inspection.
   - Refuses to add another lifecycle wrapper when one already exists anywhere in the chain.
   - Commit: `b348f8a4f1583556340b2d9cef93b6bd5741f366`

3. `usercustomize.py`
   - Version: `usercustomize-entry-pipeline-composition-2026-07-27-v42-recursion-stop`
   - Removes `shared_cycle_identity` and `scanner_v2_candidate_lifecycle_trace` from repeated watchdog reapplication.
   - Both remain installed once through the normal module registration sequence.
   - Commit: `831da522896a411121f9a7119c1e9976c4e39d28`

## Safety impact

No scanner arguments or results were changed. No entry/exit thresholds, risk limits, sizing, executable universe, positions, order placement, ML authority, or live authority were changed.

## Required Railway validation

After Railway deploys commit `831da522896a411121f9a7119c1e9976c4e39d28` or later:

1. Open `/health` and confirm service health.
2. Open `/paper/status` and confirm `auto_runner.last_error` no longer receives a newly timestamped recursion error after a normal cycle.
3. Open `/paper/self-check` and confirm it returns JSON rather than HTTP 500.
4. Open `/paper/shared-cycle-identity-status` and verify version `shared-cycle-identity-2026-07-27-v2-recursion-guard`.
5. Open `/paper/scanner-v2-candidate-lifecycle-trace-status` and verify version `scanner-v2-candidate-lifecycle-trace-2026-07-27-v2-recursion-guard`.

Do not advance blocker-coverage or ML milestones until this runtime recovery passes.