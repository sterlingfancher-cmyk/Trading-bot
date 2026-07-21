"""Scanner v2 advisory candidate-lifecycle trace.

Pass-through instrumentation around scan_signals. It records whether requested symbols
were present when a scan started and whether they appeared in returned long/short
signals. It does not alter arguments, results, thresholds, sizing, risk controls, or
order behavior. Paper diagnostics only.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, Iterable, List, Set

VERSION = "scanner-v2-candidate-lifecycle-trace-2026-07-21-v1"
DEFAULT_SYMBOLS = ["BE", "NVTS", "STX", "NUAI", "CRWV", "ONDS"]
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_LAST_TRACE: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "scan_signals"):
            return module
    return None


def _symbol(value: Any) -> str:
    raw = str(value or "").upper().strip().lstrip("$")
    clean = raw.replace(".", "").replace("-", "")
    return raw if raw and len(raw) <= 10 and clean.isalnum() else ""


def _unique(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for value in values or []:
        symbol = _symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _result_symbols(result: Any) -> Dict[str, List[str]]:
    long_symbols: List[str] = []
    short_symbols: List[str] = []
    try:
        if isinstance(result, tuple):
            long_rows = result[0] if len(result) > 0 else []
            short_rows = result[1] if len(result) > 1 else []
        elif isinstance(result, dict):
            long_rows = result.get("long_signals") or result.get("longs") or []
            short_rows = result.get("short_signals") or result.get("shorts") or []
        else:
            long_rows, short_rows = [], []
        for row in long_rows if isinstance(long_rows, list) else []:
            symbol = _symbol(row.get("symbol") if isinstance(row, dict) else row)
            if symbol:
                long_symbols.append(symbol)
        for row in short_rows if isinstance(short_rows, list) else []:
            symbol = _symbol(row.get("symbol") if isinstance(row, dict) else row)
            if symbol:
                short_symbols.append(symbol)
    except Exception:
        pass
    return {"long_signal_symbols": _unique(long_symbols), "short_signal_symbols": _unique(short_symbols)}


def _patch_scan_signals(core: Any) -> bool:
    current = getattr(core, "scan_signals", None)
    if not callable(current) or getattr(current, "_scanner_v2_lifecycle_trace_patched", False):
        return False
    original = current

    def wrapped(market):
        global _LAST_TRACE
        watch = _unique(DEFAULT_SYMBOLS)
        universe = _unique(getattr(core, "UNIVERSE", []) or [])
        started = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        before = {
            symbol: {
                "in_universe_at_scan_start": symbol in set(universe),
                "stage": "scan_invoked",
            }
            for symbol in watch
        }
        try:
            result = original(market)
        except Exception as exc:
            _LAST_TRACE = {
                "version": VERSION,
                "generated_local": started,
                "status": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "symbols": before,
            }
            raise
        signals = _result_symbols(result)
        long_set = set(signals["long_signal_symbols"])
        short_set = set(signals["short_signal_symbols"])
        for symbol, row in before.items():
            row["returned_long_signal"] = symbol in long_set
            row["returned_short_signal"] = symbol in short_set
            row["stage"] = "returned_signal" if symbol in long_set or symbol in short_set else "scan_completed_no_signal"
        _LAST_TRACE = {
            "version": VERSION,
            "generated_local": started,
            "status": "ok",
            "universe_count_at_scan_start": len(universe),
            "symbols": before,
            **signals,
        }
        return result

    wrapped._scanner_v2_lifecycle_trace_patched = True  # type: ignore[attr-defined]
    wrapped._scanner_v2_lifecycle_trace_original = original  # type: ignore[attr-defined]
    core.scan_signals = wrapped
    PATCHED_MODULE_IDS.add(id(core))
    return True


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    patched = bool(getattr(getattr(core, "scan_signals", None), "_scanner_v2_lifecycle_trace_patched", False)) if core is not None else False
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "scanner_v2_candidate_lifecycle_trace",
        "version": VERSION,
        "mode": "advisory_pass_through_instrumentation",
        "scan_signals_patched_for_diagnostics": patched,
        "latest_trace": dict(_LAST_TRACE),
        "authority": {
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_risk_or_sizing": False,
            "changes_thresholds": False,
            "core_universe_mutated": False,
            "places_orders": False,
            "alters_scan_result": False,
        },
        "next_gate": "Use the next completed scanner cycle to confirm whether STX reaches scan invocation and whether it exits with no signal.",
    }


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is not None:
        _patch_scan_signals(core)
    return status_payload(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    path = "/paper/scanner-v2-candidate-lifecycle-trace-status"
    if path not in existing:
        flask_app.add_url_rule(path, "scanner_v2_candidate_lifecycle_trace_status", lambda: jsonify(status_payload(core or _mod())))
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
