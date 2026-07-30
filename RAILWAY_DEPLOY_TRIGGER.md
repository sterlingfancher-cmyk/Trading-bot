# Railway Deployment Trigger

Updated: 2026-07-30 14:10 CDT

Purpose: create a fresh commit on `main` after the Railway outage so the service redeploys the already-committed runtime updates.

This commit does not change trading logic, signals, thresholds, sizing, risk limits, order placement, live authority, or ML authority.

Required runtime commits already on `main`:

- `19d19bfa9df5683c8c89b7c6cd85f4ac13a98b43` — deterministic breakout scanner ownership guard
- `115e921ecdfeb50fde4b4b1125787e9bb190352d` — Gunicorn activation for the guard
- `2069a448066c3cc8f9fec0f7497ee024ba6ee8c7` — chain-aware opening-surge ownership
- `b1ce0966dff681052ed851588cb927ef668ddc89` — deployment-lag handoff update

Post-deployment validation:

1. `/paper/breakout-scanner-ownership-status`
2. `/paper/opening-surge-participation-status`
3. `/paper/bear-recovery-stack-status`
4. `/paper/self-check`
