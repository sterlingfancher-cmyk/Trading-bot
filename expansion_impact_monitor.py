"""Expansion impact monitor.

Read-only monitor for the paper-only controlled expansion.

It answers:
- Did open positions move toward the new target?
- Did execution rows increase after expansion?
- Were new entries tagged as core vs paper research?
- Did drawdown, losses, state size, or ML authority warnings increase?

This module does not trade, resize, change risk controls, change ML authority,
or modify strategy behavior