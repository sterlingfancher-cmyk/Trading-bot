# Paper Underdeployment Repair — 2026-08-03

## Problem

The paper account had approximately $10,749.67 equity, $10,240.9964 cash, one DELL position, 37 scanner signals, no daily loss or drawdown, and only about 4.73% gross deployment. DELL was profitable, but the starter notional was reduced to roughly $494 because the starter allocation factor was multiplied by the ordinary portfolio allocation and bucket factor.

A component-level `pass` therefore did not mean the account was participating adequately.

## Source

- `paper_underdeployment_repair.py`
- version `paper-underdeployment-repair-2026-08-03-v1`
- startup activation in `gunicorn.conf.py`

## Repair

For already-approved paper starter entries, the module converts the starter target into an absolute final notional rather than treating the 12–18% starter target as another multiplier.

Default targets:

- risk-on: 18% of equity
- constructive: 16%
- neutral: 15%
- late neutral: 12%

The final target remains the minimum of:

- regime target
- 2% maximum modeled trade risk at the configured stop
- available cash after a 20% reserve
- remaining room under the 36% combined starter-exposure ceiling
- available cash
- existing sector and bucket exposure limits

## Two-position staging

- maximum starter positions: 2
- maximum combined exposure: 36%
- minimum spacing: 900 seconds
- second starter must differ by sector or strategy bucket
- the first position cannot be below -0.50%
- starter minimum-cash gate reduced from 85% to 75% so a correctly sized first position does not mechanically prevent a second qualified starter
- starter daily allowance raised to 2

No trade is forced. The candidate must still pass the existing scanner, score, ranking, quality, cooldown, sector, bucket, cash, risk, and execution controls.

## Diagnostics

The module persists:

- intended target percentage and notional
- original portfolio allocation percentage
- original starter allocation factor
- bucket factor
- configured stop distance
- risk-cap notional
- cash-cap notional
- combined-exposure room
- final requested notional
- executed notional and shortfall
- top candidates
- top rejected candidates
- rejection-reason counts

Status route:

`/paper/underdeployment-participation-status`

## Self-check behavior

The all-in-one self-check gains an `underdeployment_participation` component. It warns when all of the following are true:

- current or recently completed regular session
- at least 120 minutes after the open
- neutral, constructive, or risk-on mode
- clean risk state
- at least 20 scanner signals
- at least 80% cash
- less than 10% deployed
- no more than one position

This prevents an operationally healthy but materially underdeployed account from reporting a clean overall pass.

## Authority boundary

- paper only
- changes paper sizing and starter participation thresholds
- does not change global signal thresholds
- does not change the 3% daily-loss ceiling or other hard-risk limits
- does not place orders directly
- does not grant live authority
- does not grant ML authority

## Validation

- module passed local Python syntax compilation before push
- worker startup imports the module, starts its watchdog, and registers its route
- next Railway validation: `/paper/self-check`
- focused status: `/paper/underdeployment-participation-status`

Because the regular session was already closed when this repair was pushed, it applies to the next independently qualified paper entry rather than forcing a late trade.