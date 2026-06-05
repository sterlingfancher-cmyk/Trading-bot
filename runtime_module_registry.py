"""Runtime registry placeholder.

Safe fallback only. The full runtime registry package was not installed because
connector file writes were truncating during this session.
"""
VERSION = "runtime-registry-placeholder-safe"


def apply(*args, **kwargs):
    return {
        "status": "placeholder",
        "version": VERSION,
        "advisory_only": True,
        "authority_changed": False,
        "note": "Full runtime registry not installed."
    }
