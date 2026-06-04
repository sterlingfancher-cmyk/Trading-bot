"""Runtime module registry and startup patch verification.

Read-only observability for the overlay architecture. It records module imports,
startup function calls, expected diagnostic routes, and critical overlay health.
It does not trade, alter risk controls, or change ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "