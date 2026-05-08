"""WSGI entry point that directly registers shadow/auxiliary endpoints."""
from __future__ import annotations

from app import app

try:
    import sitecustomize as ml_shadow
    if hasattr(ml_shadow, "_register_routes"):
        ml_shadow._register_routes(app)
except Exception:
    pass

try:
    import eod_hybrid
    if hasattr(eod_hybrid, "_register_routes"):
        eod_hybrid._register_routes(app)
except Exception:
    pass
