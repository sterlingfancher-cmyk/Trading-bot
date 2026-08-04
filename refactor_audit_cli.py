#!/usr/bin/env python3
"""JSON-safe command-line adapter for refactor_audit.

The core audit intentionally preserves literal source values, including Python
sets. This adapter supplies deterministic JSON serialization without changing
the audit's source-analysis behavior.
"""
from __future__ import annotations

import json
from typing import Any

import refactor_audit


def _json_default(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    if isinstance(value, tuple):
        return list(value)
    return repr(value)


_ORIGINAL_DUMPS = json.dumps


def _safe_dumps(value: Any, *args: Any, **kwargs: Any) -> str:
    kwargs.setdefault("default", _json_default)
    return _ORIGINAL_DUMPS(value, *args, **kwargs)


def main() -> int:
    # refactor_audit imports the json module object, so replacing dumps here
    # safely affects only this short-lived audit process.
    json.dumps = _safe_dumps  # type: ignore[assignment]
    refactor_audit.json.dumps = _safe_dumps  # type: ignore[assignment]
    return refactor_audit.main()


if __name__ == "__main__":
    raise SystemExit(main())
