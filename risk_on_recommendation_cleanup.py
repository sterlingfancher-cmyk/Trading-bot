from __future__ import annotations

import functools
from typing import Any, Dict, List

VERSION = "risk-on-wording-cleanup-2026-05-13"
_APPLIED = False


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _symbol(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("symbol", "") or "").upper().strip()
    return str(row or "").upper().strip()


def _symbols(rows: List[Any], exclude: set[str] | None = None, limit: int = 8) -> List[str]:
    exclude = exclude or set()
    out: List[str] = []
    for row in rows:
        sym = _symbol(row)
        if not sym or sym in exclude or sym in out:
            continue
        out.append(sym)
        if len(out) >= limit:
            break
    return out


def _held_symbols(snapshot: Dict[str, Any]) -> set[str]:
    positions = snapshot.get("positions") if isinstance(snapshot.get("positions"), dict) else {}
    rows = positions.get("positions") if isinstance(positions.get("positions"), list) else []
    return {_symbol(row) for row in rows if _symbol(row)}


def _clean_recommendation_text(text: str) -> str:
    text = str(text or "").strip()
    if text.startswith("Best distinct candidates are extended and should wait for pullback/reclaim confirmation:"):
        names = text.split(":", 1)[1].strip() if ":" in text else ""
        return f"Best distinct watch candidates are extended; wait for pullback/reclaim before allowing entry: {names}"
    if text.startswith("Best distinct candidates are extended; wait for pullback/reclaim confirmation:"):
        names = text.split(":", 1)[1].strip() if ":" in text else ""
        return f"Best distinct watch candidates are extended; wait for pullback/reclaim before allowing entry: {names}"
    if "prioritize distinct confirmed setup" in text.lower():
        return text.replace("prioritize distinct confirmed setup(s)", "prioritize distinct entry-ready setup(s)")
    return text


def _dedupe_recommendations(items: List[Any]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        text = _clean_recommendation_text(str(item or ""))
        if not text:
            continue
        key = text.lower().replace("-", " ").replace("–", " ").replace("—", " ")
        if "risk on" in key and "active" in key and "long" in key:
            key = "risk_on_active_slots"
        elif "3%" in key and "5%" in key:
            key = "confirmed_setup_exposure"
        elif "partial" in key or "profit lock" in key:
            key = "partial_exits_profit_locks"
        elif "pullback" in key or "extended" in key or "chase" in key:
            key = "pullback_reclaim_wait"
        elif "score floor" in key:
            key = "score_floor"
        elif "existing holding" in key:
            key = "existing_holding_fallback"
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _priority_lists(diag: Dict[str, Any], snapshot: Dict[str, Any]) -> tuple[List[str], List[str]]:
    held = _held_symbols(snapshot)
    priority = _symbols(_as_list(diag.get("priority_distinct_symbols")), held, 8)
    eligible = [r for r in _as_list(diag.get("eligible_add_on_candidates")) if _symbol(r) and _symbol(r) not in held]
    timing = [r for r in _as_list(diag.get("watch_for_pullback_reclaim")) if _symbol(r) and _symbol(r) not in held]
    watch = _symbols(_as_list(diag.get("watch_distinct_pullback_reclaim")), held, 8)
    if not priority:
        priority = _symbols(eligible, held, 8)
    if not watch:
        watch = _symbols(timing, held, 8)
    return priority, watch


def _top_line(diag: Dict[str, Any], snapshot: Dict[str, Any], priority: List[str], watch: List[str]) -> str:
    participation = snapshot.get("risk_on_participation") if isinstance(snapshot.get("risk_on_participation"), dict) else {}
    state = diag.get("participation_state") if isinstance(diag.get("participation_state"), dict) else {}
    active = bool(participation.get("active", state.get("risk_on_active", False)))
    slots = state.get("open_additional_long_slots")
    if slots is None:
        slots = 0
    try:
        slots = int(slots)
    except Exception:
        slots = 0
    if not active:
        return "Risk-on inactive; keep standard controls."
    if slots <= 0:
        return "Risk-on active, but target long count is already filled; manage current winners."
    if priority:
        return f"Risk-on active, {slots} slot(s) open; prioritize distinct entry-ready setup(s): {', '.join(priority[:5])}."
    if watch:
        return f"Risk-on active, {slots} slot(s) open; no distinct entry is confirmed yet. Watch {', '.join(watch[:6])} for pullback/reclaim confirmation."
    return f"Risk-on active, {slots} slot(s) open; no distinct entry is confirmed yet. Wait for the next clean setup confirmation."


def cleanup_diagnostic(diag: Dict[str, Any], snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    diag = dict(diag) if isinstance(diag, dict) else {}
    priority, watch = _priority_lists(diag, snapshot)
    diag["priority_distinct_symbols"] = priority
    diag["watch_distinct_pullback_reclaim"] = watch
    diag["top_line"] = _top_line(diag, snapshot, priority, watch)
    diag["recommendation_cleanup_version"] = VERSION
    diag["recommended_actions"] = _dedupe_recommendations(_as_list(diag.get("recommended_actions")))
    return diag


def apply(*args, **kwargs) -> Dict[str, Any]:
    global _APPLIED
    if _APPLIED:
        return {"status": "ok", "version": VERSION, "already_applied": True}
    patched: List[str] = []
    try:
        import risk_on_entry_diagnostic as red
        def merge(primary, secondary):
            secondary_clean = _dedupe_recommendations(_as_list(secondary))
            return secondary_clean or _dedupe_recommendations(_as_list(primary))
        red._merge_recommendations = merge
        patched.append("risk_on_entry_diagnostic._merge_recommendations")
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc)}
    try:
        import benchmark_participation as bp
        original = getattr(bp, "build_snapshot", None)
        if callable(original) and not getattr(original, "_recommendation_cleanup_wrapped", False):
            @functools.wraps(original)
            def wrapped(*args, **kwargs):
                snap = original(*args, **kwargs)
                if isinstance(snap, dict):
                    diag = snap.get("entry_participation_diagnostic") if isinstance(snap.get("entry_participation_diagnostic"), dict) else {}
                    if diag:
                        clean = cleanup_diagnostic(diag, snap)
                        snap["entry_participation_diagnostic"] = clean
                        snap["recommended_actions"] = clean.get("recommended_actions", [])
                        snap["priority_distinct_symbols"] = clean.get("priority_distinct_symbols", [])
                        snap["watch_distinct_pullback_reclaim"] = clean.get("watch_distinct_pullback_reclaim", [])
                        snap["top_line"] = clean.get("top_line")
                        snap["recommendation_cleanup_version"] = VERSION
                return snap
            wrapped._recommendation_cleanup_wrapped = True
            bp.build_snapshot = wrapped
            patched.append("benchmark_participation.build_snapshot")
    except Exception:
        pass
    _APPLIED = True
    return {"status": "ok", "version": VERSION, "patched": patched}


def register_routes(flask_app: Any, core: Any | None = None) -> Dict[str, Any]:
    from flask import jsonify
    patch = apply()
    try:
        import benchmark_participation as bp
        import risk_on_entry_diagnostic as red
        def clean_diagnostic():
            snap = bp.build_snapshot(core, force=True)
            diag = red.status_payload(core) if hasattr(red, "status_payload") else red.build_diagnostic(core)
            return jsonify(cleanup_diagnostic(diag, snap))
        def clean_participation():
            snap = bp.build_snapshot(core, force=True)
            diag = cleanup_diagnostic(snap.get("entry_participation_diagnostic") or {}, snap)
            return jsonify({
                "status": "ok",
                "type": "market_participation_status",
                "version": getattr(bp, "VERSION", VERSION),
                "recommendation_cleanup_version": VERSION,
                "diagnostic_version": diag.get("version"),
                "generated_local": snap.get("generated_local"),
                "top_line": diag.get("top_line"),
                "benchmark_summary": snap.get("benchmarks"),
                "benchmark_data_missing": snap.get("benchmark_data_missing"),
                "benchmark_data_stale": snap.get("benchmark_data_stale"),
                "benchmark_data_ready": snap.get("benchmark_data_ready"),
                "bot_alpha": snap.get("alpha"),
                "risk_on_participation": snap.get("risk_on_participation"),
                "positions": snap.get("positions"),
                "priority_distinct_symbols": diag.get("priority_distinct_symbols", []),
                "watch_distinct_pullback_reclaim": diag.get("watch_distinct_pullback_reclaim", []),
                "entry_participation_diagnostic": diag,
                "recommended_actions": diag.get("recommended_actions", []),
            })
        flask_app.view_functions["risk_on_entry_diagnostic"] = clean_diagnostic
        flask_app.view_functions["market_participation_status"] = clean_participation
        return {"status": "ok", "version": VERSION, "registered": True, "patch": patch}
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc), "patch": patch}
