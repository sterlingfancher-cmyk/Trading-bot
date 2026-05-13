from __future__ import annotations
import contextlib, json, os, tempfile, time
from typing import Any, Dict, List, Tuple

VERSION = "state-journal-persist-2026-05-13"
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
JOURNAL_FILE = os.environ.get("TRADE_JOURNAL_FILE") or os.path.join(STATE_DIR, os.path.basename(os.environ.get("TRADE_JOURNAL_FILENAME", "trade_journal.json")))
LOCK_FILE = os.path.join(STATE_DIR or ".", ".state_io.lock")
RECEIPT_FILE = os.path.join(STATE_DIR or ".", "state_journal_repair_receipt.json")
_PATCHED: set[int] = set()
try:
    import fcntl
except Exception:
    fcntl = None

def _read(path: str) -> Dict[str, Any]:
    for i in range(4):
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            if i < 3:
                time.sleep(0.05)
    return {}

def _safe_read(path: str) -> Dict[str, Any]:
    try:
        import state_io_hardening
        if hasattr(state_io_hardening, "safe_load_json_file"):
            obj = state_io_hardening.safe_load_json_file(path, default={})
            return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    return _read(path)

def _write(path: str, obj: Dict[str, Any]) -> None:
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sjp_", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            d = os.open(folder, os.O_DIRECTORY)
            try:
                os.fsync(d)
            finally:
                os.close(d)
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

def _locks(core: Any | None) -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    try:
        import state_io_hardening
        l = getattr(state_io_hardening, "_RUN_LOCK", None)
        if l is not None:
            out.append(("state_io_run_lock", l))
    except Exception:
        pass
    try:
        l = getattr(core, "RUN_LOCK", None)
        if l is not None:
            out.append(("core_run_lock", l))
    except Exception:
        pass
    seen = set()
    ans = []
    for name, l in out:
        if id(l) not in seen and hasattr(l, "acquire") and hasattr(l, "release"):
            ans.append((name, l))
            seen.add(id(l))
    return ans

@contextlib.contextmanager
def _locked(core: Any | None):
    got: List[Tuple[str, Any]] = []
    fh = None
    try:
        for name, l in _locks(core):
            ok = False
            try:
                ok = bool(l.acquire(timeout=20))
            except TypeError:
                end = time.time() + 20
                while time.time() < end:
                    ok = bool(l.acquire(False))
                    if ok:
                        break
                    time.sleep(0.05)
            if not ok:
                raise RuntimeError(f"could_not_acquire_{name}")
            got.append((name, l))
        os.makedirs(os.path.dirname(LOCK_FILE) or ".", exist_ok=True)
        fh = open(LOCK_FILE, "a+", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield {"locks": [n for n, _ in got], "file_lock": LOCK_FILE}
    finally:
        try:
            if fh is not None and fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            if fh is not None:
                fh.close()
        except Exception:
            pass
        for _, l in reversed(got):
            try:
                l.release()
            except Exception:
                pass

def apply(guard_module: Any, core: Any | None = None) -> Dict[str, Any]:
    if guard_module is None:
        return {"status": "error", "version": VERSION, "error": "guard_module_missing"}
    if id(guard_module) in _PATCHED:
        return {"status": "ok", "version": VERSION, "already_patched": True}

    original_load = getattr(guard_module, "_load_state", None)
    original_save = getattr(guard_module, "_save_state", None)
    original_repair = getattr(guard_module, "repair_state_from_journal", None)
    original_status = getattr(guard_module, "status_payload", None)

    def disk_first_load(core_arg: Any | None = None, *args, **kwargs) -> Dict[str, Any]:
        state = _safe_read(STATE_FILE)
        if state:
            return state
        if callable(original_load):
            try:
                obj = original_load(core_arg or core, *args, **kwargs)
                return obj if isinstance(obj, dict) else {}
            except Exception:
                pass
        return {}

    def final_save(state: Dict[str, Any], core_arg: Any | None = None) -> Dict[str, Any]:
        info = {"saved_by": "core_then_direct_state_file", "patch_version": VERSION, "state_file": STATE_FILE}
        if callable(original_save):
            try:
                info["core_save_attempted"] = True
                original_save(state, core_arg or core)
                info["core_save_ok"] = True
            except Exception as exc:
                info["core_save_error"] = repr(exc)
        _write(STATE_FILE, state if isinstance(state, dict) else dict(state or {}))
        info["direct_write_ok"] = True
        try:
            info["state_file_size_bytes"] = os.path.getsize(STATE_FILE)
        except Exception:
            pass
        return info

    def status(core_arg: Any | None = None) -> Dict[str, Any]:
        payload = original_status(core_arg or core) if callable(original_status) else guard_module.build_guard(core=core_arg or core)
        if isinstance(payload, dict):
            payload["persistence_patch_version"] = VERSION
            receipt = _read(RECEIPT_FILE)
            if receipt:
                payload["last_repair_receipt"] = receipt
        return payload if isinstance(payload, dict) else {}

    def verify(symbols: List[str]) -> Dict[str, Any]:
        final = {}
        attempts = []
        for i in range(1, 4):
            final = guard_module.build_guard(_safe_read(STATE_FILE), _safe_read(JOURNAL_FILE), core=None)
            blocked = set(final.get("blocked_symbols") or [])
            clear = not any(s in blocked for s in symbols)
            attempts.append({"attempt": i, "clear": clear, "blocked_symbols": final.get("blocked_symbols")})
            if clear:
                return {"persistence_verified": True, "attempts": attempts, "post_repair_guard": final}
            time.sleep(0.1)
        return {"persistence_verified": False, "attempts": attempts, "post_repair_guard": final}

    def repair(apply: bool = False, core: Any | None = None) -> Dict[str, Any]:
        active_core = core or globals().get("_CORE")
        if not callable(original_repair):
            return {"status": "error", "version": VERSION, "message": "original_repair_missing"}
        if not apply:
            result = original_repair(apply=False, core=active_core)
            if isinstance(result, dict):
                result["persistence_patch_version"] = VERSION
                result["last_repair_receipt"] = _read(RECEIPT_FILE)
            return result if isinstance(result, dict) else {}
        try:
            with _locked(active_core) as lock_info:
                result = original_repair(apply=True, core=active_core)
                if not isinstance(result, dict):
                    result = {"status": "error", "message": "repair_returned_non_object"}
                symbols = [str(s).upper() for s in result.get("repaired_symbols", []) if s]
                check = verify(symbols)
                receipt = {
                    "status": "ok" if check.get("persistence_verified") else "warn",
                    "version": VERSION,
                    "generated_ts": int(time.time()),
                    "repaired_symbols": symbols,
                    "persistence_verified": check.get("persistence_verified"),
                    "post_repair_blocked_symbols": (check.get("post_repair_guard") or {}).get("blocked_symbols"),
                    "lock_info": lock_info,
                }
                _write(RECEIPT_FILE, receipt)
                result["persistence_patch_version"] = VERSION
                result["lock_info"] = lock_info
                result["verification"] = check
                result["persistence_verified"] = check.get("persistence_verified")
                result["post_repair_guard"] = check.get("post_repair_guard")
                result["repair_receipt_file"] = RECEIPT_FILE
                if check.get("persistence_verified"):
                    result["status"] = "ok"
                    result["message"] = "State repair applied and verified from disk. Rerun /paper/self-check."
                else:
                    result["status"] = "warn"
                    result["message"] = "State repair ran, but disk verification still shows a mismatch."
                return result
        except Exception as exc:
            return {"status": "error", "version": VERSION, "apply": bool(apply), "error": repr(exc)}

    globals()["_CORE"] = core
    guard_module._load_state = disk_first_load
    guard_module._save_state = final_save
    guard_module.status_payload = status
    guard_module.repair_state_from_journal = repair
    guard_module.STATE_JOURNAL_PERSISTENCE_PATCH_VERSION = VERSION
    _PATCHED.add(id(guard_module))
    return {"status": "ok", "version": VERSION, "state_file": STATE_FILE, "journal_file": JOURNAL_FILE}
