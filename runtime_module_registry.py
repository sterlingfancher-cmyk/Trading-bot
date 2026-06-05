VERSION='runtime-module-registry-2026-06-04-compact'
EXPECTED=['decision_audit_consolidation','ml_phase2_shadow','ml_phase25_readiness','ml_feature_journal_quality','mae_mfe_integration','state_size_watchdog','paper_controlled_expansion','post_harvest_redeployment_controller','post_harvest_entry_fallback']
ROUTES=['/paper/decision-audit-status','/paper/ml2-status','/paper/ml-readiness-status','/paper/ml-feature-journal-status','/paper/state-size-watchdog','/paper/paper-controlled-expansion-status']
def _routes(app):
    try: return sorted({getattr(r,'rule','') for r in app.url_map.iter_rules()})
    except Exception: return []
def apply(core=None):
    import sys, datetime as dt
    present=[m for m in EXPECTED if m in sys.modules]
    missing=[m for m in EXPECTED if m not in sys.modules]
    return {'status':'ok' if not missing else 'warn','overall