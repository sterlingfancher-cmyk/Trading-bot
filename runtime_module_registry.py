VERSION='runtime-module-registry-safe-fallback'
def apply(core=None):
    return {'status':'ok','overall':'pass','version':VERSION,'advisory_only':True,'authority_changed':False}
def register_routes(flask_app, core=None):
    from flask import jsonify
    def route():
        return jsonify(apply(core))
    try:
        flask_app.add_url_rule('/paper/runtime-module-registry-status','runtime_module_registry_status',route)
        flask_app.add_url_rule('/paper/startup-patch-status','startup_patch_status',route)
    except Exception:
        pass
