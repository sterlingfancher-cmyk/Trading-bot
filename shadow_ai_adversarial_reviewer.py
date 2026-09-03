from __future__ import annotations

import hashlib
import json
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from shadow_ai_research_client import (
    SCHEMA_VERSION,
    ShadowAIProvider,
    ShadowAIResearchClient,
    _iso_utc,
    _parse_timestamp,
)


VERSION = "shadow-ai-adversarial-reviewer-2026-09-02-v1"
MAX_SNAPSHOT_BYTES = 32_000


@dataclass(frozen=True, slots=True)
class ShadowAIReviewerConfig:
    enabled: bool = False
    max_items: int = 128
    max_requests_per_cycle: int = 10
    deadline_seconds: float = 30.0
    result_history_limit: int = 500

    def __post_init__(self) -> None:
        if not 1 <= int(self.max_items) <= 128:
            raise ValueError("max_items must be in [1, 128]")
        if not 1 <= int(self.max_requests_per_cycle) <= 10:
            raise ValueError("max_requests_per_cycle must be in [1, 10]")
        if not 1.0 <= float(self.deadline_seconds) <= 60.0:
            raise ValueError("deadline_seconds must be in [1, 60]")
        if not 1 <= int(self.result_history_limit) <= 500:
            raise ValueError("result_history_limit must be in [1, 500]")


class ShadowAIAdversarialReviewer:
    """Single-worker, bounded, execution-independent shadow reviewer."""

    def __init__(
        self,
        *,
        client: ShadowAIResearchClient,
        provider: ShadowAIProvider | None,
        config: ShadowAIReviewerConfig | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or ShadowAIReviewerConfig()
        self.client = client
        self.provider = provider
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._queue: queue.Queue[bytes | None] = queue.Queue(
            maxsize=self.config.max_items
        )
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._results: list[dict[str, Any]] = []
        self._latest: dict[str, Any] = {}
        self._counters = {
            "cycles_observed": 0,
            "candidates_observed": 0,
            "requests_enqueued": 0,
            "requests_dropped": 0,
            "requests_completed": 0,
            "results_join_eligible": 0,
            "results_invalid_or_unavailable": 0,
            "snapshot_errors": 0,
        }
        self._last_drop_reason: str | None = None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if not self.config.enabled:
                return self._start_result(False, "research_disabled")
            if not self.client.config.enabled:
                return self._start_result(False, "client_disabled")
            if self.provider is None:
                return self._start_result(False, "provider_unavailable")
            if self._thread is not None and self._thread.is_alive():
                return self._start_result(False, "already_started")
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._worker,
                daemon=True,
                name="shadow-ai-adversarial-reviewer",
            )
            self._thread.start()
            return self._start_result(True, "started")

    def stop(self, timeout_seconds: float = 1.0) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, float(timeout_seconds)))

    def enqueue_report(self, report: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._counters["cycles_observed"] += 1
        if not self.config.enabled:
            return self._enqueue_result("disabled", 0, 0, "research_disabled")
        thread = self._thread
        if thread is None or not thread.is_alive():
            return self._enqueue_result("disabled", 0, 0, "worker_not_started")
        requests, error = self._requests_from_report(report)
        if error:
            with self._lock:
                self._counters["snapshot_errors"] += 1
            return self._enqueue_result("invalid", 0, 0, error)

        enqueued = 0
        dropped = 0
        for request in requests:
            try:
                frozen = json.dumps(
                    request,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                if len(frozen) > MAX_SNAPSHOT_BYTES:
                    raise ValueError("snapshot_too_large")
                self._queue.put_nowait(frozen)
                enqueued += 1
            except queue.Full:
                dropped += 1
                self._last_drop_reason = "queue_full_drop_new_request"
            except (TypeError, ValueError):
                dropped += 1
                self._last_drop_reason = "invalid_snapshot"

        with self._lock:
            self._counters["candidates_observed"] += len(requests)
            self._counters["requests_enqueued"] += enqueued
            self._counters["requests_dropped"] += dropped
        status = "enqueued" if enqueued else ("dropped" if dropped else "empty")
        return self._enqueue_result(
            status,
            enqueued,
            dropped,
            self._last_drop_reason if dropped else None,
        )

    def status_payload(self) -> dict[str, Any]:
        with self._lock:
            thread = self._thread
            return {
                "status": "ok",
                "overall": "pass",
                "type": "shadow_ai_adversarial_reviewer_status",
                "version": VERSION,
                "enabled": self.config.enabled,
                "worker_started": thread is not None,
                "worker_alive": bool(thread is not None and thread.is_alive()),
                "worker_count": int(thread is not None and thread.is_alive()),
                "worker_name": thread.name if thread is not None else None,
                "queue_size": self._queue.qsize(),
                "queue_max_items": self.config.max_items,
                "max_requests_per_cycle": self.config.max_requests_per_cycle,
                "full_policy": "drop_new_request_with_telemetry",
                "execution_waits_for_result": False,
                "last_drop_reason": self._last_drop_reason,
                "counters": dict(self._counters),
                "latest_result": dict(self._latest),
                "result_history_count": len(self._results),
                "authority": {
                    "observer_only": True,
                    "rules_engine_sole_execution_authority": True,
                    "provider_calls_on_execution_thread": False,
                    "changes_strategy": False,
                    "changes_thresholds": False,
                    "changes_risk_or_sizing": False,
                    "changes_accounting_or_canonical_history": False,
                    "places_or_cancels_orders": False,
                    "blocks_or_delays_execution": False,
                    "automatic_promotion": False,
                },
            }

    def results_snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(dict(result) for result in self._results)

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                frozen = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if frozen is None:
                    return
                request = json.loads(frozen.decode("utf-8"))
                result = self.client.review(request, self.provider)
                record = self._classify_result(request, result)
                with self._lock:
                    self._latest = record
                    self._results.append(record)
                    del self._results[: -self.config.result_history_limit]
                    self._counters["requests_completed"] += 1
                    if record["join_eligible"]:
                        self._counters["results_join_eligible"] += 1
                    else:
                        self._counters["results_invalid_or_unavailable"] += 1
            except Exception as exc:
                with self._lock:
                    self._counters["requests_completed"] += 1
                    self._counters["results_invalid_or_unavailable"] += 1
                    self._latest = {
                        "status": "invalid",
                        "join_eligible": False,
                        "invalid_reason": f"worker_failure:{type(exc).__name__}",
                    }
            finally:
                self._queue.task_done()

    def _classify_result(
        self,
        request: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        identities_match = all(
            result.get(key) == request.get(key)
            for key in ("cycle_id", "candidate_id", "input_fingerprint")
        )
        deadline = _parse_timestamp(str(request.get("deadline_at") or ""))
        completed = _parse_timestamp(str(result.get("completed_at") or ""))
        timely = bool(deadline is not None and completed is not None and completed <= deadline)
        available = result.get("decision") in {"agree", "reject"}
        join_eligible = bool(identities_match and timely and available)
        if not identities_match:
            invalid_reason = "result_identity_mismatch"
        elif not timely:
            invalid_reason = "result_deadline_expired"
        elif not available:
            invalid_reason = "result_unavailable"
        else:
            invalid_reason = None
        return {
            "status": "accepted" if join_eligible else "invalid_telemetry_only",
            "join_eligible": join_eligible,
            "invalid_reason": invalid_reason,
            "cycle_id": request.get("cycle_id"),
            "candidate_id": request.get("candidate_id"),
            "input_fingerprint": request.get("input_fingerprint"),
            "rules_decision": request.get("rules_decision"),
            "symbol": request.get("symbol"),
            "side": request.get("side"),
            "deadline_at": request.get("deadline_at"),
            "result": dict(result),
            "authority": {
                "execution_input": False,
                "changes_rule_decision": False,
                "places_or_cancels_orders": False,
            },
        }

    def _requests_from_report(
        self,
        report: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not isinstance(report, Mapping):
            return [], "report_not_mapping"
        cycle_id = report.get("cycle_id")
        cycle_fingerprint = report.get("input_fingerprint")
        candidates = report.get("candidate_sample")
        if not isinstance(cycle_id, str) or not cycle_id:
            return [], "cycle_id_missing"
        if not isinstance(cycle_fingerprint, str) or not cycle_fingerprint:
            return [], "input_fingerprint_missing"
        if not isinstance(candidates, list):
            return [], "candidate_sample_missing"
        now = self._now().astimezone(timezone.utc)
        deadline = now + timedelta(seconds=self.config.deadline_seconds)
        requests: list[dict[str, Any]] = []
        for raw in candidates[: self.config.max_requests_per_cycle]:
            if not isinstance(raw, Mapping):
                continue
            symbol = str(raw.get("symbol") or "").strip().upper()
            side = str(raw.get("side") or "").strip().lower()
            if not symbol or side not in {"long", "short"}:
                continue
            candidate_identity = {
                "cycle_id": cycle_id,
                "cycle_fingerprint": cycle_fingerprint,
                "symbol": symbol,
                "side": side,
                "selected": bool(raw.get("selected")),
                "allowed": bool(raw.get("allowed")),
                "terminal_reason": str(raw.get("terminal_reason") or ""),
                "final_score": raw.get("final_score"),
                "final_size_multiplier": raw.get("final_size_multiplier"),
            }
            fingerprint = hashlib.sha256(
                json.dumps(
                    candidate_identity,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            rules_decision = (
                "enter"
                if candidate_identity["selected"]
                else ("hold" if candidate_identity["allowed"] else "reject")
            )
            requests.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "cycle_id": cycle_id,
                    "candidate_id": f"{symbol}:{side}:{fingerprint[:16]}",
                    "input_fingerprint": fingerprint,
                    "rules_decision": rules_decision,
                    "rules_decision_at": _iso_utc(now),
                    "symbol": symbol,
                    "side": side,
                    "strategy": str(raw.get("strategy_bucket") or "observed_rules"),
                    "setup": str(raw.get("terminal_reason") or "eligible_candidate"),
                    "regime": str(report.get("market_mode") or "unknown"),
                    "features": {
                        "cycle_input_fingerprint": cycle_fingerprint,
                        "signal_score": raw.get("signal_score"),
                        "final_score": raw.get("final_score"),
                        "final_size_multiplier": raw.get("final_size_multiplier"),
                        "selected": candidate_identity["selected"],
                        "allowed": candidate_identity["allowed"],
                        "terminal_reason": candidate_identity["terminal_reason"],
                        "confirmations": list(raw.get("confirmations") or []),
                    },
                    "proposed_entry": raw.get("price"),
                    "proposed_size": raw.get("final_size_multiplier"),
                    "sector": raw.get("sector"),
                    "bucket": raw.get("strategy_bucket"),
                    "volatility_state": report.get("volatility_state"),
                    "deadline_at": _iso_utc(deadline),
                }
            )
        return requests, None

    def _start_result(self, started: bool, reason: str) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": VERSION,
            "started": started,
            "reason": reason,
            "enabled": self.config.enabled,
            "worker_count": 1 if started else 0,
            "ordering": "after_runtime_composition",
        }

    def _enqueue_result(
        self,
        status: str,
        enqueued: int,
        dropped: int,
        reason: str | None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "version": VERSION,
            "enqueued": enqueued,
            "dropped": dropped,
            "reason": reason,
            "execution_waited": False,
            "provider_called_on_execution_thread": False,
        }


_GLOBAL_LOCK = threading.RLock()
_REVIEWER = ShadowAIAdversarialReviewer(
    client=ShadowAIResearchClient(),
    provider=None,
)


def install(
    *,
    client: ShadowAIResearchClient | None = None,
    provider: ShadowAIProvider | None = None,
    config: ShadowAIReviewerConfig | None = None,
) -> dict[str, Any]:
    global _REVIEWER
    with _GLOBAL_LOCK:
        if client is not None or provider is not None or config is not None:
            _REVIEWER.stop()
            _REVIEWER = ShadowAIAdversarialReviewer(
                client=client or ShadowAIResearchClient(),
                provider=provider,
                config=config,
            )
        return _REVIEWER.start()


def observe_cycle(report: Mapping[str, Any]) -> dict[str, Any]:
    return _REVIEWER.enqueue_report(report)


def status_payload() -> dict[str, Any]:
    return _REVIEWER.status_payload()
