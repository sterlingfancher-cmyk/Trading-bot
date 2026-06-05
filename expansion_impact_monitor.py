VERSION='expansion-impact-monitor-safe-fallback'

def apply(core=None):
    return {'status':'not_installed','overall':'warn','type':'expansion_impact_monitor_status','version':VERSION,'advisory_only':True,'authority_changed':False,'reason':'safe fallback only'}

def register_routes(flask_app, core=None):
    return None
