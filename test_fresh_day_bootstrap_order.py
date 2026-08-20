from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_fresh_day_guard_installs_before_legacy_wsgi_composition():
    text = (ROOT / "bootstrap_wsgi.py").read_text(encoding="utf-8")

    core_import = text.index("import app as core")
    guard_apply = text.index("pre_wsgi_fresh_day_guard = fresh_risk_day_baseline_guard.apply(core)")
    wsgi_import = text.index("import wsgi as legacy_wsgi")

    assert core_import < guard_apply < wsgi_import


def test_bootstrap_preserves_single_app_module_identity():
    text = (ROOT / "bootstrap_wsgi.py").read_text(encoding="utf-8")
    assert 'loaded_core = sys.modules.get("app")' in text
    assert 'if loaded_core is not core:' in text
    assert 'raise RuntimeError("app module identity changed during legacy WSGI import")' in text


def test_pre_wsgi_guard_failure_is_fail_closed():
    text = (ROOT / "bootstrap_wsgi.py").read_text(encoding="utf-8")
    assert 'phase="pre_wsgi_fresh_day_guard"' in text
    assert 'pre_wsgi_fresh_day_guard.get("status") == "error"' in text
    assert 'raise RuntimeError(' in text
