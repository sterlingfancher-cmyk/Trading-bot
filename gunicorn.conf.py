timeout = 120
workers = 1


def post_worker_init(worker):
    try:
        import app as core
        import run_report_guard
        run_report_guard.apply(core)
        run_report_guard.register_routes(core.app, core)
    except Exception:
        pass
