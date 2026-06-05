"""Runtime module registry status layer.

Compact read-only startup/overlay visibility for the Railway paper bot. It reports
which expected overlay modules are importable/present and which diagnostic routes
are registered. It does not trade or change strategy behavior.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "runtime