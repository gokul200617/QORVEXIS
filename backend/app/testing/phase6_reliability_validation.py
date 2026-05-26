from __future__ import annotations

import argparse
import json
import logging
import random
import threading
import time
import tracemalloc
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database.health import check_database, initialize_database
from app.database.session import Base, SessionLocal, engine
from app.models.inference_session import InferenceSession
from app.models.request_lifecycle_event import RequestLifecycleEvent
from app.models.request_log import RequestLog
from app.orchestration.lifecycle import transition_request
from app.orchestration.queue_manager import queue_manager
from app.providers.base import InferenceProvider, ProviderError
from app.reliability.integrity import integrity_registry
from app.reliability.recovery import recovery_registry, sweep_stale_executions
from app.routes.metrics import (
    metrics_diagnostics,
    metrics_lifecycle_integrity,
    metrics_recovery,
    metrics_reliability,
)
from app.services import inference_service
from app.services.failover_manager import failover_manager
from app.services.historical_metrics import historical_metrics
from app.services.provider_scorer import provider_scorer
from app.services.request_service import create_queued_request
from app.services.session_service import (
    cleanup_stale_sessions,
    enforce_session_bounds,
    get_session_memory_metrics,
)


REPORT_PATH = Path("phase6_reliability_report.json")
TEST_PREFIX = "phase6-validation"


class JsonLogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        parsed: dict[str, Any]
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError:
            parsed = {"message": message}
        parsed["level"] = record.levelname
        parsed["logger"] = record.name
        self.records.append(parsed)


@dataclass
class FakeProvider(InferenceProvider):
    name: str
    model: str = "phase6-fake-model"

    def generate_response(self, prompt: str) -> str:
        return f"phase6 synthetic response from {self.name}"


class ProviderBehavior:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.failures_remaining: dict[str, int] = {"gemini": 0, "groq": 0}
        self.timeout_delay_seconds = 0.0
        self.total_calls = 0

    def execute(self, provider_name: str, prompt: str) -> tuple[InferenceProvider, str]:
        with self.lock:
            self.total_calls += 1
            failures = self.failures_remaining.get(provider_name, 0)
            if failures > 0:
                self.failures_remaining[provider_name] = failures - 1
                raise ProviderError(f"phase6 forced {provider_name} failure")
            delay = self.timeout_delay_seconds
        if delay:
            time.sleep(delay)
        provider = FakeProvider(provider_name)
        return provider, provider.generate_response(prompt)

    def fail_next(self, provider: str, count: int) -> None:
        with self.lock:
            self.failures_remaining[provider] = self.failures_remaining.get(provider, 0) + count


provider_behavior = ProviderBehavior()


@contextmanager
def patched_provider_execution():
    original = inference_service.execute_provider
    inference_service.execute_provider = provider_behavior.execute
    try:
        yield
    finally:
        inference_service.execute_provider = original


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def db_session():
    return SessionLocal()


def create_session(db, title: str) -> InferenceSession:
    session = InferenceSession(title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def create_request(db, state: str, session_id: str | None = None, age_seconds: int = 0) -> RequestLog:
    ts = now_utc() - timedelta(seconds=age_seconds)
    request = RequestLog(
        session_id=session_id,
        prompt=f"{TEST_PREFIX} request {uuid4()}",
        response="",
        provider_used=None,
        original_provider="gemini",
        fallback_used=False,
        model_used=None,
        latency_ms=None,
        request_category="infrastructure",
        request_priority="normal",
        request_status="queued" if state == "queued" else state,
        lifecycle_state=state,
        received_at=ts,
        queued_at=ts if state in {"queued", "scheduled", "executing", "completed", "failed"} else None,
        scheduled_at=ts if state in {"scheduled", "executing", "completed", "failed"} else None,
        execution_started_at=ts if state in {"executing", "completed", "failed"} else None,
        completed_at=ts if state in {"completed", "failed", "cancelled"} else None,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    db.add(RequestLifecycleEvent(request_id=request.id, state=state, detail="phase6 setup"))
    db.commit()
    return request


def result(name: str, objective: str) -> dict[str, Any]:
    return {
        "test_name": name,
        "objective": objective,
        "execution_steps": [],
        "observed_behavior": {},
        "status": "PASS",
        "logs_errors": [],
        "suspected_root_cause": None,
        "exact_file_involved": None,
        "exact_code_region_involved": None,
        "recommended_fix": None,
        "risk_flags": [],
    }


def fail(test: dict[str, Any], message: str, **fields: Any) -> None:
    test["status"] = "FAIL"
    test["logs_errors"].append(message)
    test["observed_behavior"].update(fields)


def test_lifecycle_integrity(logs: JsonLogCapture) -> dict[str, Any]:
    test = result("TEST 1 - Lifecycle Integrity Validation", "Reject illegal terminal/backward lifecycle transitions.")
    test["execution_steps"] = [
        "Created requests in completed, failed, cancelled, and executing states.",
        "Attempted completed->queued, failed->executing, cancelled->completed, executing->scheduled.",
        "Checked state preservation, integrity registry, lifecycle violation logs, and metrics endpoint.",
    ]
    db = db_session()
    before = integrity_registry.snapshot()["violation_count"]
    attempts = []
    try:
        cases = [("completed", "queued"), ("failed", "executing"), ("cancelled", "completed"), ("executing", "scheduled")]
        for current, target in cases:
            request = create_request(db, current)
            accepted = transition_request(db, request.id, target, detail="phase6 invalid transition")
            db.refresh(request)
            attempts.append({"request_id": request.id, "from": current, "to": target, "accepted": accepted, "final_state": request.lifecycle_state})
            if accepted or request.lifecycle_state != current:
                fail(test, f"Invalid transition {current}->{target} was not safely rejected.")
        after = integrity_registry.snapshot()["violation_count"]
        violations_logged = [item for item in logs.records if item.get("event") == "lifecycle.violation"]
        metrics = metrics_lifecycle_integrity(db)
        test["observed_behavior"] = {
            "attempts": attempts,
            "integrity_violations_added": after - before,
            "lifecycle_violation_logs_seen": len(violations_logged),
            "metrics_keys": sorted(metrics.keys()),
        }
        if after - before < len(cases):
            fail(test, "Integrity registry did not record every invalid transition.")
        if len(violations_logged) < len(cases):
            fail(test, "Structured lifecycle violation logs were incomplete.")
    finally:
        db.close()
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Lifecycle guard or transition metrics failed to account for rejected transitions."
        test["exact_file_involved"] = "backend/app/reliability/lifecycle_guard.py"
        test["exact_code_region_involved"] = "validate_lifecycle_transition"
        test["recommended_fix"] = "Ensure every rejected transition records an integrity violation and emits a structured lifecycle.violation log."
        test["risk_flags"] = ["lifecycle corruption", "observability inconsistency"]
    return test


def test_recovery_sweeper() -> dict[str, Any]:
    test = result("TEST 2 - Recovery Sweeper Validation", "Detect stale scheduled/executing work and repair lifecycle state.")
    test["execution_steps"] = [
        "Created stale executing and scheduled requests older than stale_execution_seconds.",
        "Injected one stale request into queue_manager active execution state to simulate worker crash.",
        "Ran sweep_stale_executions and inspected DB state plus active execution registry.",
    ]
    db = db_session()
    active_injected = None
    try:
        stale_execution = create_request(db, "executing", age_seconds=900)
        stale_scheduled = create_request(db, "scheduled", age_seconds=900)
        active_injected = stale_execution.id
        with queue_manager._lock:
            queue_manager._active_request_ids.add(active_injected)
            queue_manager._active_executions += 1
        recovered = sweep_stale_executions()
        db.expire_all()
        rows = {row.id: row.lifecycle_state for row in db.query(RequestLog).filter(RequestLog.id.in_([stale_execution.id, stale_scheduled.id])).all()}
        diagnostics = queue_manager.diagnostics(db)
        test["observed_behavior"] = {
            "recovered_count": recovered,
            "states_after_sweep": rows,
            "active_request_ids_after_sweep": diagnostics["active_request_ids"],
            "orphaned_executions": diagnostics["orphaned_executions"],
            "recovery_registry": recovery_registry.snapshot(),
        }
        if rows.get(stale_execution.id) != "failed" or rows.get(stale_scheduled.id) != "failed":
            fail(test, "Sweeper did not mark all stale execution states failed.")
        if active_injected in diagnostics["active_request_ids"]:
            fail(test, "Sweeper repaired DB lifecycle but did not clean in-memory active execution state.")
    finally:
        if active_injected is not None:
            with queue_manager._lock:
                queue_manager._active_request_ids.discard(active_injected)
                queue_manager._active_executions = max(0, queue_manager._active_executions - 1)
        db.close()
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Recovery sweeper only updates persistent lifecycle rows and has no cleanup path for QueueManager active execution bookkeeping."
        test["exact_file_involved"] = "backend/app/reliability/recovery.py"
        test["exact_code_region_involved"] = "sweep_stale_executions"
        test["recommended_fix"] = "Add a narrow queue_manager cleanup hook for stale request ids after persistent recovery succeeds."
        test["risk_flags"] = ["lifecycle corruption", "queue corruption"]
    return test


def enqueue_requests(session_id: str, count: int, concurrent_writers: int = 16) -> list[Future]:
    queue_manager.start()
    futures: list[Future] = []
    futures_lock = threading.Lock()

    if engine.url.get_backend_name() == "sqlite":
        db = db_session()
        try:
            prepared = []
            for index in range(count):
                prompt = f"{TEST_PREFIX} queue stress {session_id} item {index} python infrastructure"
                request = create_queued_request(db, session_id=session_id, prompt=prompt, priority="normal")
                prepared.append((request.id, prompt))
        finally:
            db.close()

        def submit_prepared(item: tuple[int, str]) -> None:
            request_id, prompt = item
            future = queue_manager.enqueue(request_id, prompt, "normal", [])
            with futures_lock:
                futures.append(future)

        with ThreadPoolExecutor(max_workers=concurrent_writers) as executor:
            list(executor.map(submit_prepared, prepared))
        return futures

    def submit_one(index: int) -> None:
        prompt = f"{TEST_PREFIX} queue stress {session_id} item {index} python infrastructure"
        future: Future | None = None
        try:
            db = db_session()
            try:
                request = create_queued_request(db, session_id=session_id, prompt=prompt, priority="normal")
                future = queue_manager.enqueue(request.id, prompt, "normal", [])
            finally:
                db.close()
        except Exception as exc:
            future = Future()
            future.set_exception(exc)
        with futures_lock:
            futures.append(future)

    with ThreadPoolExecutor(max_workers=concurrent_writers) as executor:
        list(executor.map(submit_one, range(count)))
    return futures


def wait_for_futures(futures: list[Future], timeout_seconds: int) -> tuple[int, int, list[str]]:
    deadline = time.monotonic() + timeout_seconds
    completed = 0
    failed = 0
    errors: list[str] = []
    for future in futures:
        remaining = max(0.1, deadline - time.monotonic())
        try:
            future.result(timeout=remaining)
            completed += 1
        except Exception as exc:
            failed += 1
            errors.append(repr(exc))
    return completed, failed, errors[:10]


def test_queue_stress() -> dict[str, Any]:
    test = result("TEST 3 - Queue Stress Test", "Submit 100/500/1000 queued requests and verify eventual drain without duplicate execution.")
    test["execution_steps"] = [
        "Started queue workers.",
        "Submitted 100, 500, then 1000 requests using concurrent DB writers.",
        "Waited for futures and checked DB terminal counts, queue diagnostics, and duplicate lifecycle events.",
    ]
    db = db_session()
    session = create_session(db, f"{TEST_PREFIX} queue stress {uuid4()}")
    counts = [100, 500, 1000]
    observations = []
    try:
        for count in counts:
            started = time.monotonic()
            futures = enqueue_requests(session.id, count, concurrent_writers=24)
            completed, failed_count, errors = wait_for_futures(futures, timeout_seconds=180)
            elapsed = round(time.monotonic() - started, 2)
            snapshot = queue_manager.snapshot()
            rows = (
                db.query(RequestLog.lifecycle_state, RequestLog.request_status)
                .filter(RequestLog.session_id == session.id)
                .all()
            )
            terminal = sum(1 for state, _status in rows if state in {"completed", "failed", "cancelled"})
            observations.append(
                {
                    "count": count,
                    "completed_futures": completed,
                    "failed_futures": failed_count,
                    "elapsed_seconds": elapsed,
                    "queue_snapshot": snapshot,
                    "session_terminal_rows": terminal,
                    "sample_errors": errors,
                }
            )
            if failed_count:
                fail(test, f"{failed_count} futures failed during {count} request stress level.")
            if snapshot["queue_depth"] != 0:
                fail(test, f"Queue did not drain after {count} request stress level.")
            if snapshot["queue_anomalies"] != 0:
                fail(test, "Queue anomaly counter is non-zero.")
        transitions = (
            db.query(RequestLifecycleEvent.request_id, RequestLifecycleEvent.state)
            .join(RequestLog, RequestLog.id == RequestLifecycleEvent.request_id)
            .filter(RequestLog.session_id == session.id)
            .all()
        )
        seen = set()
        duplicates = []
        for request_id, state in transitions:
            key = (request_id, state)
            if key in seen and state in {"scheduled", "executing", "completed"}:
                duplicates.append({"request_id": request_id, "state": state})
            seen.add(key)
        test["observed_behavior"] = {"stress_levels": observations, "duplicate_execution_transitions": duplicates[:10]}
        if duplicates:
            fail(test, "Duplicate execution lifecycle transitions detected.")
    finally:
        db.close()
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Queue worker lifecycle path did not fully drain, rejected work, or emitted duplicate execution events under load."
        test["exact_file_involved"] = "backend/app/orchestration/queue_manager.py"
        test["exact_code_region_involved"] = "QueueManager.enqueue / QueueManager._execute_traced"
        test["recommended_fix"] = "Add idempotent lifecycle transition guards around worker execution and expose drain/backpressure diagnostics."
        test["risk_flags"] = ["queue corruption", "deadlock", "lifecycle corruption"]
    return test


def test_provider_failure_storm() -> dict[str, Any]:
    test = result("TEST 4 - Provider Failure Storm", "Force repeated provider failures and verify failover, cooldown, and scoring behavior.")
    test["execution_steps"] = [
        "Injected repeated Gemini and Groq provider failures through patched provider execution.",
        "Ran direct inference calls to exercise fallback and double-failure paths.",
        "Checked cooldown and provider score snapshots.",
    ]
    outcomes = []
    provider_behavior.fail_next("gemini", 4)
    provider_behavior.fail_next("groq", 4)
    for index in range(8):
        prompt = f"{TEST_PREFIX} provider storm {index}"
        try:
            result_value = inference_service.run_inference(prompt, [])
            outcomes.append({"index": index, "provider": result_value.provider, "fallback_used": result_value.fallback_used})
        except Exception as exc:
            outcomes.append({"index": index, "error": repr(exc)})
    failover = failover_manager.snapshot()
    scores = provider_scorer.get_all_scores()
    cooled = [item for item in failover["providers"] if item["is_cooled_down"]]
    test["observed_behavior"] = {"outcomes": outcomes, "failover": failover, "scores": scores}
    if not cooled:
        fail(test, "Provider cooldown did not activate under repeated failures.")
    if len(outcomes) > 20:
        fail(test, "Unexpected loop amplification detected.")
    score_providers = {item["provider"] for item in scores["providers"]}
    if not {"gemini", "groq"}.issubset(score_providers):
        fail(test, "Provider scoring did not update for both providers.")
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Failover/scoring state did not react consistently to injected provider failures."
        test["exact_file_involved"] = "backend/app/services/inference_service.py"
        test["exact_code_region_involved"] = "run_inference provider/fallback exception handling"
        test["recommended_fix"] = "Ensure both primary and fallback failures update failover manager and provider scorer symmetrically."
        test["risk_flags"] = ["failover instability"]
    return test


def test_session_memory() -> dict[str, Any]:
    test = result("TEST 5 - Session Memory Validation", "Validate stale session cleanup and per-session request bounds.")
    test["execution_steps"] = [
        "Created stale sessions and recent sessions.",
        "Created more requests than session_max_requests in one session.",
        "Ran cleanup_stale_sessions and enforce_session_bounds, then checked metrics.",
    ]
    db = db_session()
    try:
        stale_ids = []
        stale_time = now_utc() - timedelta(days=3)
        for index in range(20):
            session = InferenceSession(title=f"{TEST_PREFIX} stale session {index}", updated_at=stale_time, created_at=stale_time)
            db.add(session)
            db.commit()
            stale_ids.append(session.id)
            create_request(db, "completed", session_id=session.id)
        bounded = create_session(db, f"{TEST_PREFIX} bounded session")
        for index in range(95):
            create_request(db, "completed", session_id=bounded.id)
        deleted_for_bounds = enforce_session_bounds(db, bounded.id)
        cleanup_evictions = cleanup_stale_sessions(db)
        remaining_stale = db.query(InferenceSession).filter(InferenceSession.id.in_(stale_ids)).count()
        bounded_count = db.query(RequestLog).filter(RequestLog.session_id == bounded.id).count()
        metrics = get_session_memory_metrics(db)
        test["observed_behavior"] = {
            "cleanup_evictions": cleanup_evictions,
            "remaining_stale_sessions": remaining_stale,
            "bounded_session_deleted_requests": deleted_for_bounds,
            "bounded_session_request_count": bounded_count,
            "metrics": metrics,
        }
        if remaining_stale:
            fail(test, "Stale sessions remained after cleanup.")
        if bounded_count > metrics["session_max_requests"]:
            fail(test, "Session request bound was not enforced.")
    finally:
        db.close()
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Session cleanup or request bound enforcement failed to delete stale state."
        test["exact_file_involved"] = "backend/app/services/session_service.py"
        test["exact_code_region_involved"] = "cleanup_stale_sessions / enforce_session_bounds"
        test["recommended_fix"] = "Run cleanup on lifecycle entry points and make request-bound eviction deterministic per session."
        test["risk_flags"] = ["memory leak"]
    return test


def test_observability(logs: JsonLogCapture) -> dict[str, Any]:
    test = result("TEST 6 - Structured Observability Validation", "Verify logs contain fields needed to reconstruct lifecycle, scheduler, cache, and failover decisions.")
    test["execution_steps"] = [
        "Submitted a traced request through queue execution.",
        "Captured structured log events in memory.",
        "Checked required field coverage and lifecycle reconstruction.",
    ]
    db = db_session()
    try:
        session = create_session(db, f"{TEST_PREFIX} observability {uuid4()}")
        futures = enqueue_requests(session.id, 1, concurrent_writers=1)
        completed, failed_count, errors = wait_for_futures(futures, 30)
        request_rows = db.query(RequestLog).filter(RequestLog.session_id == session.id).all()
        request_id = request_rows[0].id if request_rows else None
        related = [item for item in logs.records if item.get("request_id") or item.get("event", "").startswith(("queue.", "scheduler.", "cache.", "lifecycle."))]
        required = {"request_id", "session_id", "provider", "lifecycle_state", "queue_wait_ms", "execution_duration_ms", "cache_hit", "fallback_used"}
        present = {key for item in related for key in item.keys() if key in required}
        lifecycle_events = [item.get("event") for item in related if item.get("request_id") and item.get("event")]
        test["observed_behavior"] = {
            "future_completed": completed,
            "future_failed": failed_count,
            "sample_errors": errors,
            "request_id": request_id,
            "required_fields_present": sorted(present),
            "required_fields_missing": sorted(required - present),
            "lifecycle_events_seen": lifecycle_events[-20:],
        }
        missing = required - present
        if missing:
            fail(test, f"Structured logs missing required fields: {sorted(missing)}")
    finally:
        db.close()
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Log events are structured JSON, but required trace fields are spread unevenly and session context is not propagated into queue worker traces."
        test["exact_file_involved"] = "backend/app/observability/logger.py; backend/app/orchestration/queue_manager.py"
        test["exact_code_region_involved"] = "log_event; QueueManager.enqueue/_execute"
        test["recommended_fix"] = "Carry session_id through QueuedExecution and include a common field envelope on all queue/lifecycle/cache/provider completion logs."
        test["risk_flags"] = ["observability inconsistency"]
    return test


def test_historical_metrics() -> dict[str, Any]:
    test = result("TEST 7 - Historical Metrics Validation", "Verify operational_history.jsonl append format and rolling in-memory window.")
    test["execution_steps"] = [
        "Recorded historical samples beyond the configured window.",
        "Read operational_history.jsonl tail and parsed JSON lines.",
        "Checked snapshot size and required sample fields.",
    ]
    for index in range(260):
        historical_metrics.record("phase6_validation", {"index": index, "status": "ok"})
    snapshot = historical_metrics.snapshot().get("phase6_validation", [])
    lines = Path("operational_history.jsonl").read_text(encoding="utf-8").splitlines()[-20:]
    parsed = []
    errors = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
    invalid = [item for item in parsed if "name" not in item or "sample" not in item or "recorded_at" not in item.get("sample", {})]
    test["observed_behavior"] = {"snapshot_len": len(snapshot), "tail_parse_errors": errors, "invalid_tail_records": invalid[:3]}
    if len(snapshot) > 240:
        fail(test, "Rolling in-memory historical window exceeded configured size.")
    if errors or invalid:
        fail(test, "Historical metrics JSONL contains invalid records.")
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Historical metrics persistence format or in-memory deque bounds are inconsistent."
        test["exact_file_involved"] = "backend/app/services/historical_metrics.py"
        test["exact_code_region_involved"] = "HistoricalMetricsStore.record / _append_sample"
        test["recommended_fix"] = "Validate sample envelope before append and enforce settings.historical_metrics_window on every series."
        test["risk_flags"] = ["observability inconsistency", "memory leak"]
    return test


def test_concurrency_safety() -> dict[str, Any]:
    test = result("TEST 8 - Concurrency Safety Validation", "Stress simultaneous insertion, duplicate enqueue, scheduler work, and recovery overlap.")
    test["execution_steps"] = [
        "Submitted concurrent work while recovery sweeper ran in parallel.",
        "Attempted duplicate enqueue for one request id.",
        "Checked duplicate transition events and queue diagnostics.",
    ]
    db = db_session()
    try:
        session = create_session(db, f"{TEST_PREFIX} concurrency {uuid4()}")
        stop = threading.Event()
        sweep_errors: list[str] = []

        def sweeper_loop() -> None:
            while not stop.is_set():
                try:
                    sweep_stale_executions()
                except Exception as exc:
                    sweep_errors.append(repr(exc))
                time.sleep(0.05)

        thread = threading.Thread(target=sweeper_loop, daemon=True)
        thread.start()
        futures = enqueue_requests(session.id, 120, concurrent_writers=32)
        duplicate_request = create_queued_request(db, session.id, f"{TEST_PREFIX} duplicate queue insertion python", "normal")
        first = queue_manager.enqueue(duplicate_request.id, duplicate_request.prompt, "normal", [])
        second = queue_manager.enqueue(duplicate_request.id, duplicate_request.prompt, "normal", [])
        futures.extend([first, second])
        completed, failed_count, errors = wait_for_futures(futures, 90)
        stop.set()
        thread.join(timeout=2)
        diagnostics = queue_manager.diagnostics(db)
        transitions = (
            db.query(RequestLifecycleEvent.request_id, RequestLifecycleEvent.state)
            .join(RequestLog, RequestLog.id == RequestLifecycleEvent.request_id)
            .filter(RequestLog.session_id == session.id)
            .all()
        )
        counts: dict[tuple[int, str], int] = {}
        for request_id, state in transitions:
            counts[(request_id, state)] = counts.get((request_id, state), 0) + 1
        duplicate_terminal = [{"request_id": rid, "state": state, "count": count} for (rid, state), count in counts.items() if state in {"scheduled", "executing", "completed"} and count > 1]
        test["observed_behavior"] = {
            "completed_futures": completed,
            "failed_futures": failed_count,
            "sample_errors": errors,
            "sweeper_errors": sweep_errors[:10],
            "queue_diagnostics": diagnostics,
            "duplicate_execution_transitions": duplicate_terminal[:10],
        }
        if not any("Duplicate queue insertion rejected" in error for error in errors):
            fail(test, "Duplicate enqueue was not rejected as an error.")
        if duplicate_terminal:
            fail(test, "Duplicate lifecycle transitions observed under concurrency.")
        if diagnostics["active_request_ids"]:
            fail(test, "Active executions remained after concurrency test drained.")
        if sweep_errors:
            fail(test, "Recovery sweeper raised during overlap with scheduler.")
    finally:
        db.close()
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Queue/lifecycle state is not fully idempotent under duplicate insertion or recovery overlap."
        test["exact_file_involved"] = "backend/app/orchestration/queue_manager.py; backend/app/reliability/recovery.py"
        test["exact_code_region_involved"] = "QueueManager.enqueue/_execute_traced; sweep_stale_executions"
        test["recommended_fix"] = "Keep duplicate rejection but expose it as an expected integrity signal, and guard recovery against in-flight scheduler-owned rows."
        test["risk_flags"] = ["queue corruption", "deadlock", "lifecycle corruption"]
    return test


def test_database_degradation() -> dict[str, Any]:
    test = result("TEST 9 - Database Degradation Test", "Simulate unavailable database and verify degraded reporting without process crash.")
    test["execution_steps"] = [
        "Checked real database health first.",
        "Monkeypatched database health engine to an unreachable local Postgres URL.",
        "Called health and reliability metrics with a closed/broken session where possible.",
    ]
    import app.database.health as health_module

    real_health = check_database()
    original_engine = health_module.engine
    bad_engine = create_engine("postgresql+psycopg2://postgres:bad@127.0.0.1:1/postgres?connect_timeout=1")
    degraded_health = None
    metrics_observed: dict[str, Any] = {}
    try:
        health_module.engine = bad_engine
        degraded_health = health_module.check_database()
        BadSessionLocal = sessionmaker(bind=bad_engine, autoflush=False, autocommit=False)
        bad_db = BadSessionLocal()
        bad_db.close()
        for name, func in {
            "reliability": metrics_reliability,
            "recovery": metrics_recovery,
            "diagnostics": metrics_diagnostics,
        }.items():
            try:
                metrics_observed[name] = func(bad_db)
            except Exception as exc:
                metrics_observed[name] = {"raised": repr(exc)}
    finally:
        health_module.engine = original_engine
    test["observed_behavior"] = {"real_health": real_health, "degraded_health": degraded_health, "metrics_observed": metrics_observed}
    if degraded_health[0] is not False:
        fail(test, "Database health did not report unavailable during simulated outage.")
    raised = {name: value for name, value in metrics_observed.items() if "raised" in value}
    if raised:
        fail(test, "Some reliability endpoints raised instead of returning degraded payloads.", raised=raised)
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Database degradation fallback only covers SQLAlchemyError inside route functions and not dependency/session acquisition failure modes."
        test["exact_file_involved"] = "backend/app/routes/metrics.py; backend/app/database/health.py"
        test["exact_code_region_involved"] = "metrics_reliability/metrics_recovery/metrics_diagnostics; check_database"
        test["recommended_fix"] = "Add endpoint-level degraded wrappers that include dependency/session construction failures and avoid requiring live DB sessions for in-memory reliability status."
        test["risk_flags"] = ["observability inconsistency", "lifecycle corruption"]
    return test


def test_long_runtime_stability() -> dict[str, Any]:
    test = result("TEST 10 - Long Runtime Stability Test", "Run continuous queue churn, cache activity, session growth, and provider failures for a bounded soak.")
    test["execution_steps"] = [
        "Ran 60 seconds of continuous small-batch traffic.",
        "Injected intermittent provider failures.",
        "Sampled queue depth, thread count, memory, and active executions.",
    ]
    db = db_session()
    samples = []
    futures: list[Future] = []
    try:
        session = create_session(db, f"{TEST_PREFIX} long runtime {uuid4()}")
        deadline = time.monotonic() + 60
        index = 0
        while time.monotonic() < deadline:
            if index % 15 == 0:
                provider_behavior.fail_next(random.choice(["gemini", "groq"]), 1)
            prompt = f"{TEST_PREFIX} long runtime churn {index % 25} python cache activity"
            request = create_queued_request(db, session.id, prompt, "normal")
            futures.append(queue_manager.enqueue(request.id, prompt, "normal", []))
            if index % 20 == 0:
                _current, usage = tracemalloc.get_traced_memory()
                samples.append({"t": round(time.monotonic(), 2), "queue": queue_manager.snapshot(), "threads": threading.active_count(), "maxrss": usage})
            index += 1
            time.sleep(0.05)
        completed, failed_count, errors = wait_for_futures(futures, 120)
        final_snapshot = queue_manager.snapshot()
        diagnostics = queue_manager.diagnostics(db)
        _current, usage = tracemalloc.get_traced_memory()
        test["observed_behavior"] = {
            "submitted": len(futures),
            "completed_futures": completed,
            "failed_futures": failed_count,
            "sample_errors": errors,
            "samples": samples,
            "final_queue": final_snapshot,
            "final_diagnostics": diagnostics,
            "final_maxrss": usage,
            "thread_count": threading.active_count(),
        }
        if final_snapshot["queue_depth"] != 0:
            fail(test, "Queue did not drain after long runtime test.")
        if diagnostics["active_request_ids"]:
            fail(test, "Active executions remained after long runtime drain.")
        if threading.active_count() > 40:
            fail(test, "Thread count grew beyond expected bounds.")
        if failed_count > len(futures) * 0.2:
            fail(test, "Failure rate exceeded 20 percent during bounded soak.")
    finally:
        db.close()
    if test["status"] == "FAIL":
        test["suspected_root_cause"] = "Long-running churn left queue/active state unstable or failure rate too high."
        test["exact_file_involved"] = "backend/app/orchestration/queue_manager.py"
        test["exact_code_region_involved"] = "QueueManager._worker/_execute_traced"
        test["recommended_fix"] = "Add explicit worker health, bounded queue controls, and orphan cleanup tied to recovery."
        test["risk_flags"] = ["memory leak", "deadlock", "queue corruption"]
    return test


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-heavy", action="store_true", help="Skip 500/1000 queue stress and 60s soak.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    tracemalloc.start()
    capture = JsonLogCapture()
    capture.setLevel(logging.INFO)
    logging.getLogger().addHandler(capture)
    for handler in logging.getLogger().handlers:
        if handler is not capture:
            handler.setLevel(logging.WARNING)

    if engine.url.get_backend_name() == "sqlite":
        Base.metadata.create_all(bind=engine)
    else:
        initialize_database()
    db_ok, db_error = check_database()
    if not db_ok:
        raise RuntimeError(f"Database unavailable: {db_error}")

    with patched_provider_execution():
        tests = [
            test_lifecycle_integrity(capture),
            test_recovery_sweeper(),
        ]
        if args.skip_heavy:
            tests.append(result("TEST 3 - Queue Stress Test", "Skipped by --skip-heavy."))
            tests[-1]["status"] = "SKIPPED"
        else:
            tests.append(test_queue_stress())
        tests.extend(
            [
                test_provider_failure_storm(),
                test_session_memory(),
                test_observability(capture),
                test_historical_metrics(),
                test_concurrency_safety(),
                test_database_degradation(),
            ]
        )
        if args.skip_heavy:
            tests.append(result("TEST 10 - Long Runtime Stability Test", "Skipped by --skip-heavy."))
            tests[-1]["status"] = "SKIPPED"
        else:
            tests.append(test_long_runtime_stability())

    report = {
        "generated_at": now_utc().isoformat(),
        "database_health": {"ok": db_ok, "error": db_error},
        "tests": tests,
        "summary": {
            "pass": sum(1 for item in tests if item["status"] == "PASS"),
            "fail": sum(1 for item in tests if item["status"] == "FAIL"),
            "skipped": sum(1 for item in tests if item["status"] == "SKIPPED"),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    print(str(REPORT_PATH.resolve()))
    return 1 if report["summary"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
