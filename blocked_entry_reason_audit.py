"""Mobile-safe blocked-entry reason audit.

Advisory-only diagnostic layer for answering: "Market is green; why no trades?"

This module reads the existing state/scanner audit and summarizes blocked entries,
rejected candidates, top blocked symbols, and likely blocker categories. It does
not call heavy market-data routes, does not place trades, does not lower filters,
and does not change ML or live-trading authority.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List, Tuple

VERSION = "blocked-entry-reason-audit-2026-06-30-v3-placeholder-cleanup"
REGISTERED_APP_IDS: set[int] = set()

MAX_ROWS = 80
MAX_TOP_SYMBOLS = 20
MAX_TOP_REASONS = 12
MAX_SYMBOL_ROLLUP = 15

MISSING_REASON_MARKERS = {
    "reason_not_available_in_state_snapshot",
    "top_blocked_symbol_reason_not_in_mobile_snapshot",
    "reason_missing_after_row_compaction",
}

MOMENTUM_WATCH_SYMBOLS = [
    "RKLB", "RDW", "LUNR", "MNTS", "ASTS", "SPCX", "SPCE", "PL", "BKSY", "SATL", "SPIR",
    "AMD", "AVGO", "MU", "LRCX", "NVTS", "NBIS", "GEV", "STX", "WDC", "HPE", "DELL", "TER",
    "CIFR", "HIVE", "HUT", "RIOT", "CLSK", "MARA", "BTDR", "WULF", "IREN", "CORZ",
]


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    try:
        state = core.load_state() if core is not None and hasattr(core, "load_state") else {}
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _portfolio(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    try:
        pf = getattr(core, "portfolio", None)
        return pf if isinstance(pf, dict) else {}
    except Exception:
        return {}


def _dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _symbol(value: Any) -> str:
    try:
        return str(value or "").upper().strip()
    except Exception:
        return ""


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _add_count(counts: Dict[str, int], key: str) -> None:
    key = str(key or "unknown").strip() or "unknown"
    counts[key] = int(counts.get(key, 0)) + 1


def _top_counts(counts: Dict[str, int], limit: int) -> List[Dict[str, Any]]:
    return [
        {"value": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _flatten_symbols(obj: Any, out: set[str] | None = None, max_items: int = 5000) -> set[str]:
    if out is None:
        out = set()
    seen = 0

    def walk(value: Any) -> None:
        nonlocal seen
        if seen >= max_items:
            return
        seen += 1
        if isinstance(value, dict):
            for key in ("symbol", "ticker", "asset", "name"):
                if key in value:
                    sym = _symbol(value.get(key))
                    if 1 <= len(sym) <= 12 and sym.replace(".", "").replace("-", "").isalnum():
                        out.add(sym)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            sym = _symbol(value)
            if 1 <= len(sym) <= 12 and sym.replace(".", "").replace("-", "").isalnum():
                out.add(sym)

    walk(obj)
    return out


def _candidate_sections(state: Dict[str, Any], pf: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    sections: List[Tuple[str, Dict[str, Any]]] = []
    for source, container in (("state", state), ("portfolio", pf)):
        if not isinstance(container, dict):
            continue
        for key in (
            "scanner_audit",
            "decision_audit",
            "decision_audit_summary",
            "latest_cycle",
            "latest_redeployment",
            "post_harvest_redeployment",
            "entry_decision_visibility",
            "paper_controlled_expansion",
            "market_surge_deployment",
            "controlled_redeployment_starter_sleeve",
            "core_entry_pipeline",
        ):
            section = container.get(key)
            if isinstance(section, dict):
                sections.append((f"{source}.{key}", section))
    return sections


def _extract_rows_from_section(source: str, section: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    keys = (
        "blocked_entries",
        "blocked_post_harvest_entries",
        "rejected_signals",
        "rejected_top_candidates",
        "rejected_candidates",
        "top_candidates_reviewed",
        "top_blocked_candidates",
        "blocked_candidates",
        "blocked_symbols_detail",
        "rejected_preview",
        "selected_candidate",
    )
    for key in keys:
        value = section.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    row = dict(item)
                else:
                    row = {"symbol": item}
                row.setdefault("source", f"{source}.{key}")
                row.setdefault("source_key", key)
                rows.append(row)
        elif isinstance(value, dict):
            if key == "selected_candidate":
                row = dict(value)
                row.setdefault("source", f"{source}.{key}")
                row.setdefault("source_key", key)
                rows.append(row)
            else:
                for sym, item in value.items():
                    if isinstance(item, dict):
                        row = dict(item)
                    else:
                        row = {"detail": item}
                    row.setdefault("symbol", sym)
                    row.setdefault("source", f"{source}.{key}")
                    row.setdefault("source_key", key)
                    rows.append(row)
    return rows


def _collect_top_blocked_symbols(scanner: Dict[str, Any], sections: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
    out: List[str] = []

    def add(sym: Any) -> None:
        symbol = _symbol(sym)
        if symbol and symbol not in out:
            out.append(symbol)

    raw_top_blocked = scanner.get("top_blocked_symbols")
    if isinstance(raw_top_blocked, list):
        for item in raw_top_blocked:
            add(item.get("symbol") if isinstance(item, dict) else item)

    for _, section in sections:
        top_blocked = section.get("top_blocked_symbols")
        if isinstance(top_blocked, list):
            for item in top_blocked:
                add(item.get("symbol") if isinstance(item, dict) else item)

    return out[:MAX_TOP_SYMBOLS]


def _nested_reason(row: Dict[str, Any]) -> str:
    nested_keys = ("quality_info", "participation_valve", "score_gate", "rotation_info", "core_participation_valve")
    parts: List[str] = []
    for key in nested_keys:
        obj = row.get(key)
        if not isinstance(obj, dict):
            continue
        for reason_key in ("reason", "status", "decision", "message", "action"):
            value = obj.get(reason_key)
            if isinstance(value, str) and value.strip():
                parts.append(f"{key}.{reason_key}={value.strip()}")
                break
        failed = obj.get("failed_floors")
        if isinstance(failed, list) and failed:
            parts.append(f"{key}.failed_floors=" + ",".join(str(x) for x in failed if x))
    return ";".join(parts)


def _reason_from_row(row: Dict[str, Any]) -> str:
    base = ""
    for key in (
        "block_reason",
        "blocked_reason",
        "rejection_reason",
        "reject_reason",
        "entry_block_reason",
        "reason",
        "status_reason",
        "decision_reason",
        "guardrail_reason",
        "why_blocked",
        "message",
    ):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            base = value.strip()
            break
        if isinstance(value, list) and value:
            base = ",".join(str(v) for v in value if v)
            break
    if not base:
        reasons = row.get("reasons") or row.get("block_reasons") or row.get("warnings")
        if isinstance(reasons, list) and reasons:
            base = ",".join(str(v) for v in reasons if v)
    nested = _nested_reason(row)
    if base and nested and base not in MISSING_REASON_MARKERS:
        return f"{base};{nested}"
    if base:
        return base
    if nested:
        return nested
    return "reason_not_available_in_state_snapshot"


def _is_missing_reason(reason: str) -> bool:
    text = str(reason or "").strip().lower()
    return (
        text in MISSING_REASON_MARKERS
        or "reason_not_available" in text
        or "reason_not_in_mobile_snapshot" in text
        or "reason_missing" in text
    )


def _category(reason: str) -> str:
    text = str(reason or "").lower()
    if _is_missing_reason(text):
        return "reason_detail_missing"
    checks = [
        ("extension_chase", ("extend", "chase", "above_day_open", "near_high", "gap", "overstretched", "extended_")),
        ("missing_or_stale_price", ("missing_price", "stale", "no_data", "not_enough_bars", "quote", "empty_price")),
        ("risk_control", ("risk", "halt", "drawdown", "self_defense", "daily_loss", "loss_streak")),
        ("quality_score", ("quality", "score", "threshold", "not_confirmed", "weak", "floor", "candidate")),
        ("max_positions", ("max_position", "positions_full", "max positions", "open_positions")),
        ("sector_or_bucket_exposure", ("sector", "bucket", "exposure", "concentration")),
        ("cooldown", ("cooldown", "recent", "ttl")),
        ("cash_gate", ("cash", "buying_power", "allocation")),
        ("market_context", ("bear", "risk_off", "market", "regime", "breadth", "vix", "rates", "futures_bias")),
        ("already_open", ("already", "open position", "held")),
    ]
    for label, needles in checks:
        if any(needle in text for needle in needles):
            return label
    return "other_or_unclassified"


def _compact_row(row: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol") or row.get("ticker") or row.get("asset"))
    reason = _reason_from_row(row)
    bucket = row.get("bucket") or row.get("symbol_bucket")
    if not bucket and symbol:
        try:
            bucket_map = getattr(core or _mod(), "SYMBOL_BUCKET", {})
            if isinstance(bucket_map, dict):
                bucket = bucket_map.get(symbol)
        except Exception:
            bucket = None
    return {
        "symbol": symbol or "UNKNOWN",
        "reason": reason,
        "category": _category(reason),
        "reason_detail_available": not _is_missing_reason(reason),
        "source": row.get("source"),
        "source_key": row.get("source_key"),
        "score": row.get("score") or row.get("signal_score") or row.get("quality_score") or row.get("rank_score"),
        "rank_score": row.get("rank_score") or row.get("core_entry_rank_score"),
        "price": row.get("price") or row.get("last_price") or row.get("entry_price"),
        "pct_change": row.get("pct_change") or row.get("change_pct") or row.get("day_change_pct"),
        "bucket": bucket,
        "sector": row.get("sector"),
        "side": row.get("side"),
    }


def _count_visible_rows(section: Dict[str, Any]) -> int | None:
    if not isinstance(section, dict):
        return None
    candidates: List[int] = []
    for key in ("blocked_entries", "blocked_candidates", "top_blocked_candidates", "blocked_symbols_detail"):
        obj = section.get(key)
        if isinstance(obj, list) or isinstance(obj, dict):
            candidates.append(len(obj))
    for key in ("blocked_entries_count", "blocked_count", "blocked_candidates_count"):
        value = _safe_int(section.get(key), -1)
        if value >= 0:
            candidates.append(value)
    return max(candidates) if candidates else None


def _reason_coverage(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    missing = sum(1 for row in rows if not bool(row.get("reason_detail_available")))
    available = total - missing
    return {
        "visible_rows": total,
        "rows_with_actionable_reason": available,
        "rows_missing_reason_detail": missing,
        "actionable_reason_coverage_pct": round((available / total) * 100.0, 2) if total else 0.0,
    }


def _symbol_reason_rollup(rows: List[Dict[str, Any]], top_symbols: List[str]) -> List[Dict[str, Any]]:
    wanted = [s for s in top_symbols if s]
    if not wanted:
        counts: Dict[str, int] = {}
        for row in rows:
            _add_count(counts, row.get("symbol") or "UNKNOWN")
        wanted = [row["value"] for row in _top_counts(counts, MAX_SYMBOL_ROLLUP)]
    out: List[Dict[str, Any]] = []
    for symbol in wanted[:MAX_SYMBOL_ROLLUP]:
        symbol_rows = [row for row in rows if row.get("symbol") == symbol]
        if not symbol_rows:
            out.append({
                "symbol": symbol,
                "rows": 0,
                "top_reason": "reason_detail_missing",
                "top_category": "reason_detail_missing",
                "reason_detail_available": False,
            })
            continue
        reason_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        actionable_reason_counts: Dict[str, int] = {}
        actionable_category_counts: Dict[str, int] = {}
        for row in symbol_rows:
            reason = row.get("reason") or "unknown"
            category = row.get("category") or "unknown"
            _add_count(reason_counts, reason)
            _add_count(category_counts, category)
            if row.get("reason_detail_available"):
                _add_count(actionable_reason_counts, reason)
                _add_count(actionable_category_counts, category)
        top_reason = _top_counts(actionable_reason_counts or reason_counts, 1)[0]["value"]
        top_category = _top_counts(actionable_category_counts or category_counts, 1)[0]["value"]
        best_score = None
        for row in symbol_rows:
            score = _safe_float(row.get("score"), None)
            if score is not None:
                best_score = score if best_score is None else max(best_score, score)
        out.append({
            "symbol": symbol,
            "rows": len(symbol_rows),
            "top_reason": top_reason,
            "top_category": top_category,
            "reason_detail_available": any(bool(row.get("reason_detail_available")) for row in symbol_rows),
            "best_visible_score": round(best_score, 6) if best_score is not None else None,
        })
    return out


def build_payload(core: Any = None, state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    core = core or _mod()
    state = state if isinstance(state, dict) else _state(core)
    pf = _portfolio(core)

    scanner = _dict(state.get("scanner_audit") or pf.get("scanner_audit"))
    decision = _dict(state.get("decision_audit") or pf.get("decision_audit") or state.get("decision_audit_summary"))
    positions = _dict(state.get("positions") or pf.get("positions"))
    sections = _candidate_sections(state, pf)

    rows: List[Dict[str, Any]] = []
    for source, section in sections:
        rows.extend(_extract_rows_from_section(source, section))

    compact_rows: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        compact = _compact_row(row, core)
        key = (compact.get("symbol"), compact.get("reason"), compact.get("source_key"))
        if key in seen:
            continue
        seen.add(key)
        compact_rows.append(compact)
        if len(compact_rows) >= MAX_ROWS:
            break

    top_blocked_symbols = _collect_top_blocked_symbols(scanner, sections)
    detailed_symbols = {row.get("symbol") for row in compact_rows if row.get("symbol")}
    for symbol in top_blocked_symbols:
        if symbol not in detailed_symbols and len(compact_rows) < MAX_ROWS:
            compact_rows.append({
                "symbol": symbol,
                "reason": "top_blocked_symbol_reason_not_in_mobile_snapshot",
                "category": "reason_detail_missing",
                "reason_detail_available": False,
                "source": "scanner_audit.top_blocked_symbols",
                "source_key": "top_blocked_symbols",
                "score": None,
                "rank_score": None,
                "price": None,
                "pct_change": None,
                "bucket": None,
                "sector": None,
                "side": None,
            })

    symbol_counts: Dict[str, int] = {}
    reason_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    bucket_counts: Dict[str, int] = {}
    for row in compact_rows:
        _add_count(symbol_counts, row.get("symbol") or "UNKNOWN")
        _add_count(reason_counts, row.get("reason") or "unknown")
        _add_count(category_counts, row.get("category") or "unknown")
        if row.get("bucket"):
            _add_count(bucket_counts, str(row.get("bucket")))

    scanner_symbols = _flatten_symbols(scanner)
    decision_symbols = _flatten_symbols(decision)
    open_symbols = {_symbol(symbol) for symbol in positions.keys()}
    if not top_blocked_symbols:
        top_blocked_symbols = [row["value"] for row in _top_counts(symbol_counts, MAX_TOP_SYMBOLS)]

    watched_seen = sorted({s for s in MOMENTUM_WATCH_SYMBOLS if s in scanner_symbols or s in decision_symbols or s in symbol_counts})
    watched_blocked = sorted({s for s in MOMENTUM_WATCH_SYMBOLS if s in symbol_counts or s in top_blocked_symbols})

    blocked_count = scanner.get("blocked_entries_count") or decision.get("blocked_entries_count")
    if blocked_count is None:
        blocked_count = _count_visible_rows(scanner)
    if blocked_count is None:
        blocked_count = _count_visible_rows(decision)
    if blocked_count is None and compact_rows:
        blocked_count = len([row for row in compact_rows if row.get("source_key") not in {"rejected_signals", "rejected_candidates", "rejected_preview"}])

    coverage = _reason_coverage(compact_rows)
    symbol_rollup = _symbol_reason_rollup(compact_rows, top_blocked_symbols)
    missing_reason_symbols = [row["symbol"] for row in symbol_rollup if not row.get("reason_detail_available")]
    missing_reason_rows_sample = [row for row in compact_rows if not row.get("reason_detail_available")][:10]
    unclassified_sample = [row for row in compact_rows if row.get("category") == "other_or_unclassified"][:10]

    no_trade_read = "No blocked-entry rows were available in the mobile state snapshot."
    if compact_rows:
        top_category = _top_counts(category_counts, 1)
        if top_category:
            no_trade_read = f"Most visible blocker category: {top_category[0]['value']} ({top_category[0]['count']} rows)."
        if coverage.get("rows_missing_reason_detail"):
            no_trade_read += f" Reason-detail coverage {coverage.get('actionable_reason_coverage_pct')}%."
    elif top_blocked_symbols:
        no_trade_read = "Top blocked symbols are visible, but row-level reasons were not available in the mobile state snapshot."

    next_actions = [
        "Use this summary to identify whether green movers were blocked by extension, quality, exposure, cooldown, missing price, or risk controls.",
        "Do not loosen risk blindly; only adjust the specific blocker if it repeats across clean outcomes.",
    ]
    if coverage.get("rows_missing_reason_detail"):
        next_actions.append("Persist full blocker rows before symbol-only top blocked rollups when reason_detail_missing appears.")
    if category_counts.get("extension_chase"):
        next_actions.append("Extension/chase blocks mean the bot is avoiding late green candles; wait for pullback/reclaim evidence before loosening.")
    if category_counts.get("quality_score"):
        next_actions.append("Quality-score blocks should be reviewed against later MAE/MFE outcomes before lowering floors.")
    if category_counts.get("missing_or_stale_price"):
        next_actions.append("Missing/stale price blocks should be fixed through data availability, not by weakening entry gates.")

    payload = {
        "status": "ok",
        "overall": "pass",
        "type": "blocked_entry_reason_audit_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "trading_authority": "none",
        "ml_authority": "shadow_only",
        "does_not_place_trades": True,
        "does_not_lower_thresholds": True,
        "signals_found": scanner.get("signals_found") or decision.get("signals_found"),
        "blocked_entries_count": blocked_count,
        "rejected_signals_count": decision.get("rejected_signals_count") or scanner.get("rejected_signals_count"),
        "entries_count": decision.get("entries_count"),
        "open_positions_count": len(open_symbols),
        "top_blocked_symbols": top_blocked_symbols[:MAX_TOP_SYMBOLS],
        "visible_blocked_rows_count": len(compact_rows),
        "reason_coverage": coverage,
        "missing_reason_detail_count": coverage.get("rows_missing_reason_detail"),
        "missing_reason_detail_symbols": missing_reason_symbols[:MAX_TOP_SYMBOLS],
        "missing_reason_rows_sample": missing_reason_rows_sample,
        "top_symbols_by_rows": _top_counts(symbol_counts, MAX_TOP_SYMBOLS),
        "top_reasons": _top_counts(reason_counts, MAX_TOP_REASONS),
        "top_categories": _top_counts(category_counts, MAX_TOP_REASONS),
        "top_buckets": _top_counts(bucket_counts, MAX_TOP_REASONS),
        "symbol_reason_rollup": symbol_rollup,
        "top_blocked_symbol_details": symbol_rollup[:MAX_TOP_SYMBOLS],
        "unclassified_rows_sample": unclassified_sample,
        "watched_momentum_symbols_seen": watched_seen,
        "watched_momentum_symbols_blocked": watched_blocked,
        "blocked_rows_sample": compact_rows[:25],
        "no_trade_read": no_trade_read,
        "next_actions": next_actions,
    }
    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "overall": "pass",
        "type": "blocked_entry_reason_audit_apply_status",
        "version": VERSION,
        "advisory_only": True,
        "authority_changed": False,
        "routes": ["/paper/blocked-entry-reason-audit-status"],
        "trading_authority": "none",
        "ml_authority": "shadow_only",
        "improves_reason_coverage": True,
        "cleans_symbol_only_placeholders": True,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/blocked-entry-reason-audit-status" not in existing:
        flask_app.add_url_rule(
            "/paper/blocked-entry-reason-audit-status",
            "blocked_entry_reason_audit_status",
            lambda: jsonify(build_payload(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
