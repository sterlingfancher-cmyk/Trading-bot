"""Compatibility status alias for the paper exit price-integrity guard."""
from __future__ import annotations
from typing import Any, Dict
import paper_exit_price_integrity_guard as _impl

VERSION = _impl.VERSION


def apply(core: Any = None) -> Dict[str, Any]:
    return _impl.apply(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    out = dict(_impl.status_payload(core))
    out["hook_applied"] = out.get("status") == "ok"
    return out


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return _impl.register_routes(flask_app, core)
