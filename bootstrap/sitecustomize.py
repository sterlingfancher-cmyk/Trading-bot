"""Guarded Python startup loader for the Railway web process.

Python imports ``sitecustomize`` before Gunicorn and the WSGI application. This
shim establishes the advisory-research boundary, selects a real mounted state
volume when one is available, defers the first automatic market cycle until
runtime composition is complete, installs the paper-entry epoch timestamp guard,
starts the rules-gated ML recommendation ledger, and loads the legacy startup
helpers without executing their eager pre-app registration or busy retry thread.

No trading formulas, thresholds, sizing, risk limits, live authority, or ML
execution authority are changed.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

VERSION = "guarded-sitecustomize-bootstrap-2026-08-04-v6-root-loaded-ml-counterfactual-ledger"
_TRUE = {"1", "true", "yes", "on"}


def _mount_points() -> list[Path]:
    points: list[Path] = []
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 6:
                continue
            value = fields[4].replace("\\040", " ")
            point = Path(value)
            if point not in points:
                points.append(point)
    except Exception:
        pass
    return points


def _writable_distinct_mount(path: Path) -> bool:
    try:
        path = path.resolve()
        if not path.is_dir() or not os.access(path, os.W_OK):
            return False
        if path != Path("/") and path in _mount_points():
            return True
        return path.stat().st_dev != Path("/").stat().st_dev
    except Exception:
        return False


def _state_mount_candidate() -> Path | None:
    for name in ("STATE_DIR", "PERSISTENT_STATE_DIR", "RAILWAY_VOLUME_MOUNT_PATH"):
        value = os.environ.get(name)
        if value:
            path = Path(value).expanduser()
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            return path.resolve()

    preferred: list[Path] = []
    others: list[Path] = []
    excluded_prefixes = ("/proc", "/sys", "/dev", "/run", "/etc", "/tmp")
    for point in _mount_points():
        text = str(point)
        if point == Path("/") or text.startswith(excluded_prefixes):
            continue
        if not _writable_distinct_mount(point):
            continue
        lowered = text.lower()
        if any(token in lowered for token in ("data", "state", "storage", "volume")):
            preferred.append(point)
        else:
            others.append(point)
    candidates = preferred + others
    return candidates[0].resolve() if candidates else None


def _configure_state_environment() -> dict[str, Any]:
    candidate = _state_mount_candidate()
    if candidate is None:
        os.environ.setdefault("STATE_PERSISTENCE_CONTRACT", "volume_required")
        return {
            "configured": False,
            "state_dir": None,
            "reason": "no_distinct_writable_mount_detected",
        }
    os.environ["STATE_DIR"] = str(candidate)
    os.environ.setdefault("STATE_FILENAME", "state.json")
    os.environ["STATE_PERSISTENCE_CONTRACT"] = "mounted_volume_detected"
    return {
        "configured": True,
        "state_dir": str(candidate),
        "reason": "explicit_or_detected_distinct_mount",
    }


def _defer_auto_runner() -> dict[str, Any]:
    enabled = os.environ.get("DEFER_AUTO_RUN_UNTIL_RUNTIME_REGISTRATION", "true").lower() in _TRUE
    requested = os.environ.get("AUTO_RUN_ENABLED", "true")
    if enabled:
        os.environ["AUTO_RUN_REQUESTED"] = requested
        os.environ["AUTO_RUN_ENABLED"] = "false"
        os.environ["AUTO_RUN_DEFERRED_BOOTSTRAP"] = "true"
    return {
        "enabled": enabled,
        "requested": requested,
        "app_import_value": os.environ.get("AUTO_RUN_ENABLED"),
    }


def _isolate_heavy_research() -> bool:
    allow = os.environ.get("WEB_WORKER_ALLOW_HEAVY_RESEARCH", "false").lower() in _TRUE
    if allow:
        return False
    os.environ["PERFORMANCE_AUDIT_AUTO_BACKTEST_ENABLED"] = "false"
    os.environ["PERFORMANCE_AUDIT_V2_AUTO_BACKTEST_ENABLED"] = "false"
    os.environ["PERFORMANCE_AUDIT_V2_ENABLED"] = "false"
    return True


def _start_entry_time_guard() -> dict[str, Any]:
    try:
        import paper_underdeployment_time_guard as guard

        return guard.start_guard()
    except Exception as exc:
        return {
            "status": "warn",
            "overall": "warn",
            "version": "paper-underdeployment-time-guard-unavailable",
            "patched": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def _start_ml_counterfactual_ledger() -> dict[str, Any]:
    try:
        path = Path(__file__).resolve().parents[1] / "ml_recommendation_counterfactual_ledger.py"
        spec = importlib.util.spec_from_file_location(
            "_trading_bot_ml_counterfactual_ledger", path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to create ML counterfactual ledger spec")
        ledger = importlib.util.module_from_spec(spec)
        sys.modules["_trading_bot_ml_counterfactual_ledger"] = ledger
        spec.loader.exec_module(ledger)
        return ledger.start_bootstrap_watchdog()
    except Exception as exc:
        return {
            "status": "warn",
            "overall": "warn",
            "version": "ml-counterfactual-ledger-unavailable",
            "started": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


STATE_BOOTSTRAP = _configure_state_environment()
AUTO_RUN_BOOTSTRAP = _defer_auto_runner()
RESEARCH_ISOLATED = _isolate_heavy_research()
ENTRY_TIME_GUARD = _start_entry_time_guard()
ML_COUNTERFACTUAL_LEDGER = _start_ml_counterfactual_ledger()
_ROOT = Path(__file__).resolve().parents[1]
_LEGACY_PATH = _ROOT / "sitecustomize.py"
_LEGACY_MODULE_NAME = "_trading_bot_legacy_sitecustomize"
_LEGACY_STARTUP_TAIL = """_register_all()
threading.Thread(target=_watchdog, daemon=True).start()
"""


def _load_legacy() -> Any:
    if not _LEGACY_PATH.is_file():
        raise RuntimeError(f"legacy sitecustomize missing: {_LEGACY_PATH}")

    source = _LEGACY_PATH.read_text(encoding="utf-8")
    if _LEGACY_STARTUP_TAIL not in source:
        raise RuntimeError("legacy sitecustomize startup tail not found")
    source = source.replace(
        _LEGACY_STARTUP_TAIL,
        "# Eager registration and the busy watchdog are suppressed by the guarded bootstrap.\n",
        1,
    )

    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, _LEGACY_PATH)
    if spec is None:
        raise RuntimeError("unable to create legacy sitecustomize spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module
    exec(compile(source, str(_LEGACY_PATH), "exec"), module.__dict__)
    return module


LEGACY_MODULE = _load_legacy()

# Preserve compatibility for explicit ``import sitecustomize`` calls in the
# WSGI bootstrap. Public and private registration helpers remain available.
for _name, _value in vars(LEGACY_MODULE).items():
    if _name.startswith("__"):
        continue
    globals().setdefault(_name, _value)

GUARDED_BOOTSTRAP_STATUS = {
    "version": VERSION,
    "research_isolated": RESEARCH_ISOLATED,
    "state_bootstrap": STATE_BOOTSTRAP,
    "auto_run_bootstrap": AUTO_RUN_BOOTSTRAP,
    "entry_time_guard": ENTRY_TIME_GUARD,
    "ml_counterfactual_ledger": ML_COUNTERFACTUAL_LEDGER,
    "legacy_loaded": True,
    "legacy_version": getattr(LEGACY_MODULE, "VERSION", None),
    "eager_registration_suppressed": True,
    "legacy_watchdog_suppressed": True,
    "flask_constructor_registration_preserved": True,
    "changes_trading_authority": False,
    "changes_ml_execution_authority": False,
}
