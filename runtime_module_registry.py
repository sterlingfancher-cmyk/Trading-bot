"""Runtime module registry and startup verification.

Read-only observability layer for the overlay-based architecture. It records
which auxiliary modules imported, which startup hooks were attempted, which
routes appear registered, and whether critical overlays are present.

It never trades, changes risk controls, grants ML authority, or modifies
strategy behavior.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "runtime-module-registry-2026-06-