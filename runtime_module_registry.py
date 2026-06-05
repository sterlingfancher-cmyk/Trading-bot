"""Runtime module registry and startup verification.

Read-only observability for the overlay architecture. It reports which critical
modules are imported, which expected diagnostic routes are present, and whether
startup verification is healthy. It never trades or changes authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict,