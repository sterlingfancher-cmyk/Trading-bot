"""Minimal runtime module registry."""
from __future__ import annotations
import datetime as dt
VERSION="runtime-module-registry-2026-06-04-v4-minimal"

def _now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def payload():
    return {"status":"ok","overall":"pass","type":"runtime_module_registry_status","version":VERSION,"generated_local":_now