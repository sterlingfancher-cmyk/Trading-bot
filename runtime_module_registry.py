"""Runtime module registry - compact safe version."""
from __future__ import annotations
import datetime as dt, importlib, os
from typing import Any, Dict

VERSION = "runtime-module-registry-2026-06-04-v3-safe"
IMPORTANT = [
    "state_io_hardening", "runner_safety", "trade_journal", "state_journal_guard",
    "decision_audit_consolidation", "ml_phase2_shadow", "ml_phase25_readiness",
    "ml_feature_journal_quality", "mae_mfe_integration", "state_size_watchdog",
   