from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


class DeferredBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module_name = "bootstrap_wsgi_listener_test"
        spec = importlib.util.spec_from_file_location(
            cls.module_name,
            ROOT / "bootstrap_wsgi.py",
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load bootstrap_wsgi.py")
        cls.env_patch = patch.dict(
            os.environ,
            {
                "DEFERRED_WSGI_START_DELAY_SECONDS": "10",
                "PERFORMANCE_AUDIT_V2_ENABLED": "false",
            },
            clear=False,
        )
        cls.env_patch.start()
        module = importlib.util.module_from_spec(spec)
        sys.modules[cls.module_name] = module
        spec.loader.exec_module(module)
        cls.module = module

    @classmethod
    def tearDownClass(cls) -> None:
        timer = getattr(cls.module, "_LOADER_THREAD", None)
        if timer is not None and hasattr(timer, "cancel"):
            timer.cancel()
        sys.modules.pop(cls.module_name, None)
        cls.env_patch.stop()

    def _request(self, path: str) -> tuple[str, dict]:
        captured: dict = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        body = b"".join(
            self.module.app({"PATH_INFO": path}, start_response)
        )
        return str(captured.get("status")), json.loads(body.decode("utf-8"))

    def test_bootstrap_status_responds_before_legacy_loader(self) -> None:
        status, payload = self._request("/bootstrap-status")
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["version"], self.module.VERSION)
        self.assertEqual(payload["phase"], "bootstrap_scheduled")
        self.assertFalse(payload["delegate_ready"])
        self.assertTrue(payload["loader_thread_started"])
        self.assertEqual(payload["loader_start_delay_seconds"], 10.0)

    def test_root_responds_while_application_is_loading(self) -> None:
        status, payload = self._request("/")
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["status"], "loading")
        self.assertFalse(payload["delegate_ready"])

    def test_non_bootstrap_route_returns_bounded_503(self) -> None:
        status, payload = self._request("/paper/self-check")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(payload["requested_path"], "/paper/self-check")
        self.assertIn("still loading", payload["message"])

    def test_module_does_not_import_legacy_runtime_before_delay(self) -> None:
        self.assertNotIn("wsgi", self.module.__dict__)
        self.assertIsNone(self.module._DELEGATE)

    def test_delay_is_bounded(self) -> None:
        with patch.dict(os.environ, {"DEFERRED_WSGI_START_DELAY_SECONDS": "500"}):
            self.assertEqual(self.module._loader_delay_seconds(), 10.0)
        with patch.dict(os.environ, {"DEFERRED_WSGI_START_DELAY_SECONDS": "0"}):
            self.assertEqual(self.module._loader_delay_seconds(), 0.1)


if __name__ == "__main__":
    unittest.main()
