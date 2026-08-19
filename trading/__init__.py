"""Future canonical trading-core interfaces.

This package is introduced shadow-only by Stable Paper Core v3. Importing it
must not start runners, place orders, read providers, or mutate persisted state.
"""

__all__ = ["state"]
