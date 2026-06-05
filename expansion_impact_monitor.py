"""Safe fallback for expansion impact monitor.

The full observed-outcome fix was not installed because the connector truncated the file write.
This fallback is valid Python and intentionally advisory-only.
"""
VERSION = "expansion-impact-monitor-safe-fallback"
REGISTERED_APP_IDS = set()

def apply(core=None):
    return {"status": "not_installed", "overall": "warn", "type": "expansion_impact_monitor_status", "version": VERSION, "advisory_only": True, "authority_changed": False, "reason": "safe fallback only"}

def register_routes(flask_app, core=None):
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    def status_route():
        return jsonify(apply(core))
    try:
        existing = {getattr(r, "rule", "") for r in flask_app