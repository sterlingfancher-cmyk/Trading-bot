VERSION='runtime-module-registry-safe-valid'

def apply(core=None):
    return dict(status='ok',overall='pass',version=VERSION,advisory_only=True,authority_changed=False)

def register_routes(flask_app,core=None):
    from flask import jsonify
    def a():
        return jsonify(apply(core))
    for p,e in [('/paper/runtime-module-registry-status','runtime_module_registry_status'),('/paper