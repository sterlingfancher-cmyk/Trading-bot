"""Runtime persistence contract for paper state.

The startup bootstrap selects a mounted volume before app.py imports. This module
then validates the selected path, migrates a richer legacy local state when safe,
reloads a richer persistent snapshot into the in-memory portfolio, and exposes a
bounded status endpoint. It does not fabricate or reconstruct missing trades.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

VERSION = "state-persistence-contract-2026-08-04-v1"
_LOCK = threading.RLock()
_APPLIED: set[int] = set()
_LAST: Dict[str, Any] = {}


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _richness(state: Dict[str, Any]) -> tuple[int, int, int, int, float]:
    positions = _dict(state.get("positions"))
    trades = state.get("trades") if isinstance(state.get("trades"), list) else []
    history = state.get("history") if isinstance(state.get("history"), list) else []
    reports = _dict(state.get("reports"))
    report_count = len(reports.get("intraday_history") or []) + len(reports.get("daily_history") or [])
    try:
        equity_delta = abs(float(state.get("equity", 10000.0)) - 10000.0)
    except Exception:
        equity_delta = 0.0
    return (len(positions), len(trades), len(history), report_count, equity_delta)


def _materially_richer(candidate: Dict[str, Any], baseline: Dict[str, Any]) -> bool:
    candidate_score = _richness(candidate)
    baseline_score = _richness(baseline)
    if candidate_score[:4] > baseline_score[:4]:
        return True
    return candidate_score[4] > baseline_score[4] + 0.01


def _mount_points() -> list[str]:
    points: list[str] = []
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 6:
                continue
            mount = fields[4].replace("\\040", " ")
            if mount not in points:
                points.append(mount)
    except Exception:
        pass
    return points


def _is_distinct_mount(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        resolved = str(Path(path).resolve())
        if resolved in _mount_points() and resolved != "/":
            return True
        return os.stat(resolved).st_dev != os.stat("/").st_dev
    except Exception:
        return False


def _configured_dir(core: Any) -> str | None:
    for value in (
        os.environ.get("STATE_DIR"),
        os.environ.get("PERSISTENT_STATE_DIR"),
        os.environ.get("RAILWAY_VOLUME_MOUNT_PATH"),
        getattr(core, "STATE_DIR", None),
    ):
        if isinstance(value, str) and value.strip():
            return str(Path(value.strip()).resolve())
    return None


def _legacy_candidates(state_file: str) -> Iterable[str]:
    seen: set[str] = set()
    for candidate in (
        "/app/state.json",
        str(Path.cwd() / "state.json"),
        str(Path(state_file).with_name("state.json")),
    ):
        resolved = str(Path(candidate).resolve())
        if resolved == str(Path(state_file).resolve()) or resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _replace_portfolio(core: Any, loaded: Dict[str, Any]) -> bool:
    portfolio = getattr(core, "portfolio", None)
    if not isinstance(portfolio, dict) or not isinstance(loaded, dict):
        return False
    portfolio.clear()
    portfolio.update(loaded)
    return True


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    with _LOCK:
        state_file = str(Path(getattr(core, "STATE_FILE", "state.json")).resolve())
        configured_dir = _configured_dir(core)
        persistent_mount = bool(configured_dir and _is_distinct_mount(configured_dir))
        current = _dict(getattr(core, "portfolio", {}))
        on_disk = _read_json(state_file)
        migration: Dict[str, Any] = {"performed": False, "source": None, "reason": None}
        reloaded = False

        if persistent_mount:
            Path(configured_dir).mkdir(parents=True, exist_ok=True)
            if not on_disk:
                for candidate_path in _legacy_candidates(state_file):
                    candidate = _read_json(candidate_path)
                    if candidate and _materially_richer(candidate, current):
                        try:
                            shutil.copy2(candidate_path, state_file)
                            backup = state_file + ".bak"
                            shutil.copy2(candidate_path, backup)
                            on_disk = candidate
                            migration = {
                                "performed": True,
                                "source": candidate_path,
                                "destination": state_file,
                                "reason": "richer_legacy_state_migrated_to_mounted_volume",
                            }
                        except Exception as exc:
                            migration = {
                                "performed": False,
                                "source": candidate_path,
                                "reason": f"migration_failed:{type(exc).__name__}:{exc}",
                            }
                        break
            if on_disk and _materially_richer(on_disk, current):
                reloaded = _replace_portfolio(core, on_disk)
            try:
                save = getattr(core, "save_state", None)
                if callable(save):
                    save(getattr(core, "portfolio", current))
                if Path(state_file).is_file() and not Path(state_file + ".bak").is_file():
                    shutil.copy2(state_file, state_file + ".bak")
            except Exception:
                pass

        _APPLIED.add(id(core))
        _LAST = {
            "status": "ok",
            "overall": "pass" if persistent_mount else "warn",
            "version": VERSION,
            "generated_local": _now(),
            "state_file": state_file,
            "configured_dir": configured_dir,
            "persistent_mount_detected": persistent_mount,
            "state_file_exists": Path(state_file).is_file(),
            "backup_exists": Path(state_file + ".bak").is_file(),
            "in_memory_richness": _richness(_dict(getattr(core, "portfolio", {}))),
            "on_disk_richness": _richness(_read_json(state_file)),
            "migration": migration,
            "reloaded_richer_persistent_state": reloaded,
            "recovery_limitation": (
                None if persistent_mount else
                "No distinct mounted volume was detected. Code cannot make the Railway application filesystem durable; attach a volume and set STATE_DIR to its mount path."
            ),
        }
        return dict(_LAST)


def status_payload(core: Any = None) -> Dict[str, Any]:
    if core is not None and id(core) not in _APPLIED:
        return apply(core)
    return {
        "status": "ok" if _LAST else "pending",
        "type": "state_persistence_contract",
        **dict(_LAST),
        "authority": {
            "restores_only_existing_state": True,
            "fabricates_missing_state": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/state-persistence-contract-status" not in existing:
        flask_app.add_url_rule(
            "/paper/state-persistence-contract-status",
            "state_persistence_contract_status",
            lambda: jsonify(status_payload(core)),
        )
