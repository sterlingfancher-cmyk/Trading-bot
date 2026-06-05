VERSION='missed-mover-audit-safe-fallback'

def apply(core=None):
    return {'status':'not_installed','overall':'warn','type':'missed_mover_audit_status','version':VERSION,'advisory_only':True,'authority_changed':False}

def register_routes(flask_app, core=None):
    return None
