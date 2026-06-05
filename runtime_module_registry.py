"""Compact runtime module registry.

Read-only startup visibility for the overlay architecture. This module reports
which important overlays are importable and which optional diagnostic routes are
registered. It does not trade, patch strategy logic, change risk controls, or
grant ML authority.
"""
from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
from typing import Any, Dict, List

VERSION = "runtime-module-registry-2026-06-04-v2-compact