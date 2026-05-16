"""Self-check compact telemetry enrichment.

Patches self_check._compact_payload at runtime so newer adaptive/governance
endpoints show actionable summary fields in /paper/self-check instead of only
status/type/version.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "self-check-enrichment-2026-05-16-strategy-scorecard"
PATCHED_MODULE_IDS: set[int] = set()


def _safe_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _safe_list(obj: Any) -> list[Any]:
    return obj if isinstance(obj, list) else []


def _base(payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ["status", "type", "version", "generated_local", "time", "enabled", "live_authority"]:
        if key in payload:
            out[key] = payload.get(key)
    return out


def enrich(path: str, payload: Dict[str, Any], original=None) -> Dict[str, Any]:
    compact = original(path, payload) if callable(original) else _base(payload)
    if not isinstance(compact, dict):
        compact = _base(payload)
    if not isinstance(payload, dict):
        return compact

    if path in {"/paper/ml-readiness-status", "/paper/ml-phase25-status"}:
        compact.update({
            "phase": payload.get("phase"),
            "phase3a_ready": payload.get("phase3a_ready"),
            "phase3a_live_authority_allowed": payload.get("phase3a_live_authority_allowed"),
            "gates_passed": payload.get("gates_passed"),
            "gates_failed": payload.get("gates_failed"),
            "recommendation": payload.get("recommendation"),
        })
        execution = _safe_dict(payload.get("execution_summary"))
        scanner = _safe_dict(payload.get("scanner_summary"))
        compact["execution_summary"] = {
            "execution_rows": execution.get("execution_rows"),
            "exit_rows": execution.get("exit_rows"),
            "profit_factor": execution.get("profit_factor"),
            "win_rate": execution.get("win_rate"),
        }
        compact["scanner_summary"] = {"estimated_total_decisions": scanner.get("estimated_total_decisions")}
    elif path in {"/paper/trade-quality-status", "/paper/mae-mfe-status"}:
        summary = _safe_dict(payload.get("summary"))
        compact["summary"] = {
            "graded_trades": summary.get("graded_trades") or payload.get("graded_trades"),
            "average_quality_score": summary.get("average_quality_score"),
            "grade_counts": summary.get("grade_counts"),
            "mae_complete_count": summary.get("mae_complete_count") or payload.get("mae_complete_count"),
            "mfe_complete_count": summary.get("mfe_complete_count") or payload.get("mfe_complete_count"),
            "mae_mfe_complete": summary.get("mae_mfe_complete") if "mae_mfe_complete" in summary else payload.get("mae_mfe_complete"),
        }
    elif path in {"/paper/intratrade-path-status", "/paper/position-path-status"}:
        compact.update({
            "active_positions_tracked": payload.get("active_positions_tracked"),
            "closed_paths_archived": payload.get("closed_paths_archived"),
            "active_paths_count": len(_safe_list(payload.get("active_paths"))),
            "closed_path_tail_count": len(_safe_list(payload.get("closed_path_tail"))),
        })
    elif path in {"/paper/mae-mfe-integration-status", "/paper/adaptive-exit-recommendations"}:
        summary = _safe_dict(payload.get("summary"))
        compact.update({
            "active_recommendations_count": payload.get("active_recommendations_count"),
            "ml_rows_enriched": payload.get("ml_rows_enriched"),
            "active_positions_with_path": summary.get("active_positions_with_path"),
            "strong_path_count": summary.get("strong_path_count"),
            "weak_path_count": summary.get("weak_path_count"),
            "tighten_stop_count": summary.get("tighten_stop_count"),
            "trail_winner_count": summary.get("trail_winner_count"),
        })
    elif path in {"/paper/adaptive-ml-status", "/paper/walk-forward-ml-status", "/paper/symbol-personality-status", "/paper/exit-reward-status"}:
        summary = _safe_dict(payload.get("summary"))
        walk = _safe_dict(payload.get("walk_forward"))
        compact.update({
            "summary": summary,
            "walk_forward": {
                "status": walk.get("status"),
                "formal_walk_forward_passed": walk.get("formal_walk_forward_passed"),
                "train_days": walk.get("train_days"),
                "test_days": walk.get("test_days"),
                "test_rows": walk.get("test_rows"),
                "proxy_test_win_rate": walk.get("proxy_test_win_rate"),
            },
            "active_confidence_count": len(_safe_list(payload.get("active_confidence_tail"))),
            "exit_reward_count": len(_safe_list(payload.get("exit_reward_tail"))),
        })
    elif path in {
        "/paper/adaptive-portfolio-status",
        "/paper/bayesian-confidence-status",
        "/paper/regime-cluster-status",
        "/paper/volatility-state-status",
        "/paper/correlation-governor-status",
        "/paper/capital-allocator-status",
        "/paper/ml-ensemble-status",
        "/paper/reward-decay-status",
        "/paper/strategy-rotation-status",
    }:
        bayes = _safe_dict(payload.get("bayesian_confidence"))
        regime = _safe_dict(payload.get("rolling_regime_cluster"))
        vol = _safe_dict(payload.get("volatility_state"))
        corr = _safe_dict(payload.get("portfolio_correlation_governor"))
        alloc = _safe_dict(payload.get("adaptive_capital_allocator"))
        ensemble = _safe_dict(payload.get("ml_ensemble_vote"))
        reward = _safe_dict(payload.get("reinforcement_reward_decay"))
        sequence = _safe_dict(payload.get("trade_sequence_memory"))
        rotation = _safe_dict(payload.get("dynamic_strategy_rotation"))
        compact.update({
            "overall_posterior_win_prob": bayes.get("overall_posterior_win_prob"),
            "bayes_alpha": bayes.get("alpha"),
            "bayes_beta": bayes.get("beta"),
            "regime_cluster": regime.get("cluster"),
            "volatility_state": vol.get("volatility_state"),
            "correlation_status": corr.get("status"),
            "capital_multiplier": alloc.get("recommended_capital_multiplier"),
            "ensemble_consensus": ensemble.get("consensus"),
            "ensemble_score": ensemble.get("score"),
            "recent_reward_score": reward.get("recent_reward_score"),
            "behavioral_state": sequence.get("behavioral_state"),
            "promotion_count": rotation.get("promotion_count"),
            "demotion_count": rotation.get("demotion_count"),
        })
    elif path in {"/paper/state-size-watchdog", "/paper/telemetry-retention-status"}:
        compact.update({
            "state_size_mb": payload.get("state_size_mb"),
            "warn_mb": payload.get("warn_mb"),
            "critical_mb": payload.get("critical_mb"),
            "level": payload.get("level"),
            "recommendation": payload.get("recommendation"),
            "automatic_pruning_enabled": _safe_dict(payload.get("retention_policy")).get("automatic_pruning_enabled"),
        })
    elif path in {"/paper/advisory-authority-status", "/paper/live-authority-guard-status"}:
        compact.update({
            "status_level": payload.get("status_level"),
            "allow_experimental_live_authority": payload.get("allow_experimental_live_authority"),
            "unsafe_authority_findings_count": payload.get("unsafe_authority_findings_count"),
            "all_authority_findings_count": payload.get("all_authority_findings_count"),
            "recommendation": payload.get("recommendation"),
        })
    elif path in {"/paper/strategy-label-schema-status", "/paper/setup-label-quality-status"}:
        coverage = _safe_dict(payload.get("coverage"))
        compact.update({
            "level": payload.get("level"),
            "rows_checked": coverage.get("rows_checked"),
            "complete_rows": coverage.get("complete_rows"),
            "partial_rows": coverage.get("partial_rows"),
            "missing_rows": coverage.get("missing_rows"),
            "complete_coverage_pct": coverage.get("complete_coverage_pct"),
            "required_fields": payload.get("required_fields"),
        })
    elif path in {"/paper/strategy-label-propagation-status", "/paper/canonical-strategy-label-status"}:
        compact.update({
            "targets_checked": payload.get("targets_checked"),
            "rows_changed": payload.get("rows_changed"),
            "complete_rows": payload.get("complete_rows"),
            "partial_rows": payload.get("partial_rows"),
            "missing_rows": payload.get("missing_rows"),
            "complete_coverage_pct": payload.get("complete_coverage_pct"),
            "recommendation": payload.get("recommendation"),
        })
    elif path in {"/paper/strategy-scorecard-status", "/paper/strategy-id-scorecards", "/paper/strategy-promotion-candidates"}:
        top = _safe_list(payload.get("top_scorecards"))[:3]
        compact.update({
            "strategy_count": payload.get("strategy_count"),
            "promotion_candidates_count": payload.get("promotion_candidates_count"),
            "demotion_candidates_count": payload.get("demotion_candidates_count"),
            "collect_more_data_count": payload.get("collect_more_data_count"),
            "top_scorecards": top,
            "recommendation": payload.get("recommendation"),
        })
    return compact


def apply(self_check_module: Any = None) -> Dict[str, Any]:
    if self_check_module is None:
        try:
            import self_check as self_check_module  # type: ignore
        except Exception:
            return {"status": "not_applied", "version": VERSION, "reason": "self_check_missing"}
    if id(self_check_module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True}
    original = getattr(self_check_module, "_compact_payload", None)
    if not callable(original):
        return {"status": "not_applied", "version": VERSION, "reason": "compact_payload_missing"}

    def patched_compact_payload(path, payload):
        return enrich(path, payload, original=original)

    patched_compact_payload._self_check_enrichment_patched = True  # type: ignore[attr-defined]
    setattr(self_check_module, "_compact_payload", patched_compact_payload)
    PATCHED_MODULE_IDS.add(id(self_check_module))
    return {"status": "ok", "version": VERSION, "patched": True}
