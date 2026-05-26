import logging
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count
from time import perf_counter

from app.database.session import SessionLocal
from app.observability.logger import log_event
from app.observability.tracing import get_request_id, trace_context
from app.orchestration.capacity import provider_capacity
from app.orchestration.lifecycle import COMPLETED, EXECUTING, FAILED, QUEUED, SCHEDULED, transition_request
from app.orchestration.scheduler import priority_weight, select_adaptive_provider
from app.providers import ProviderError
from app.reliability.integrity import integrity_registry
from app.reliability.recovery import recovery_registry
from app.services.dedup_tracker import dedup_tracker
from app.services.historical_metrics import historical_metrics
from app.services.inference_service import InferenceResult, run_inference
from app.services.request_service import mark_request_failed, mark_request_success
from app.services.response_cache import response_cache
from app.settings import settings

logger = logging.getLogger("qorvexis.queue")


@dataclass(order=True)
class QueuedExecution:
    priority_sort: int
    sequence: int
    request_id: int = field(compare=False)
    prompt: str = field(compare=False)
    memory_context: list[dict[str, str]] = field(compare=False)
    selected_provider: str = field(compare=False)
    queued_at: datetime = field(compare=False)
    future: Future = field(compare=False)
    correlation_id: str = field(compare=False)


class QueueManager:
    def __init__(self) -> None:
        self._queue: queue.PriorityQueue[QueuedExecution] = queue.PriorityQueue()
        self._sequence = count()
        self._started = False
        self._lock = threading.Lock()
        self._active_executions = 0
        self._completed_count = 0
        self._failed_count = 0
        self._queue_wait_total_ms = 0
        self._execution_total_ms = 0
        self._queued_request_ids: set[int] = set()
        self._active_request_ids: set[int] = set()
        self._queue_anomalies = 0

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for index in range(settings.max_concurrent_requests):
            thread = threading.Thread(target=self._worker, name=f"qorvexis-worker-{index}", daemon=True)
            thread.start()
        log_event(logger, "info", "queue.start", workers=settings.max_concurrent_requests)

    def enqueue(
        self,
        request_id: int,
        prompt: str,
        priority: str,
        memory_context: list[dict[str, str]],
    ) -> Future:
        selected_provider = select_adaptive_provider(prompt)
        is_duplicate = dedup_tracker.is_duplicate(prompt)
        dedup_tracker.record(prompt)
        future: Future = Future()

        with self._lock:
            if request_id in self._queued_request_ids or request_id in self._active_request_ids:
                self._queue_anomalies += 1
                integrity_registry.record_violation(
                    request_id=request_id,
                    current_state=QUEUED,
                    attempted_state=QUEUED,
                    reason="duplicate_queue_insertion",
                )
                future.set_exception(RuntimeError("Duplicate queue insertion rejected."))
                return future
            self._queued_request_ids.add(request_id)

        execution = QueuedExecution(
            priority_sort=priority_weight(priority),
            sequence=next(self._sequence),
            request_id=request_id,
            prompt=prompt,
            memory_context=memory_context,
            selected_provider=selected_provider,
            queued_at=datetime.now(timezone.utc),
            future=future,
            correlation_id=get_request_id(),
        )
        self._queue.put(execution)
        provider_capacity.mark_queued(selected_provider)
        log_event(
            logger,
            "info",
            "queue.enqueue",
            request_id=request_id,
            priority=priority,
            provider=selected_provider,
            queue_depth=self._queue.qsize(),
            deduplicated=is_duplicate,
        )
        return future

    def snapshot(self) -> dict:
        with self._lock:
            total_finished = self._completed_count + self._failed_count
            return {
                "queue_depth": self._queue.qsize(),
                "active_executions": self._active_executions,
                "completed_count": self._completed_count,
                "failed_count": self._failed_count,
                "average_queue_wait_ms": round(self._queue_wait_total_ms / total_finished, 2)
                if total_finished
                else 0,
                "average_execution_duration_ms": round(self._execution_total_ms / total_finished, 2)
                if total_finished
                else 0,
                "queue_anomalies": self._queue_anomalies,
            }

    def diagnostics(self, db=None) -> dict:
        with self._queue.mutex:
            queued_items = list(self._queue.queue)
        now = datetime.now(timezone.utc)
        with self._lock:
            active_ids = sorted(self._active_request_ids)
            queued_ids = sorted(self._queued_request_ids)
            anomalies = self._queue_anomalies

        orphaned_executions = []
        if db is not None and active_ids:
            from app.models.request_log import RequestLog

            rows = (
                db.query(RequestLog.id, RequestLog.lifecycle_state)
                .filter(RequestLog.id.in_(active_ids))
                .all()
            )
            state_by_id = {row.id: row.lifecycle_state for row in rows}
            orphaned_executions = [
                {"request_id": request_id, "state": state_by_id.get(request_id)}
                for request_id in active_ids
                if state_by_id.get(request_id) not in {"executing", "fallback_executing"}
            ]

        return {
            "queued_request_ids": queued_ids,
            "active_request_ids": active_ids,
            "queue_anomalies": anomalies,
            "orphaned_executions": orphaned_executions,
            "queued_items": [
                {
                    "request_id": item.request_id,
                    "provider": item.selected_provider,
                    "priority_sort": item.priority_sort,
                    "queued_for_ms": round((now - item.queued_at).total_seconds() * 1000),
                }
                for item in queued_items[:50]
            ],
        }

    def _worker(self) -> None:
        while True:
            execution = self._queue.get()
            self._execute(execution)
            self._queue.task_done()

    def _execute(self, execution: QueuedExecution) -> None:
        with trace_context(request_id=execution.correlation_id):
            self._execute_traced(execution)

    def _execute_traced(self, execution: QueuedExecution) -> None:
        provider_capacity.mark_dequeued(execution.selected_provider)
        queue_wait_ms = round(
            (datetime.now(timezone.utc) - execution.queued_at).total_seconds() * 1000
        )
        db = SessionLocal()
        started = perf_counter()
        cache_hit = False
        try:
            with self._lock:
                self._queued_request_ids.discard(execution.request_id)
                self._active_request_ids.add(execution.request_id)
                self._active_executions += 1

            if not transition_request(db, execution.request_id, SCHEDULED):
                raise RuntimeError("Lifecycle transition rejected before scheduling.")
            if not transition_request(db, execution.request_id, EXECUTING):
                raise RuntimeError("Lifecycle transition rejected before execution.")
            semaphore = provider_capacity.acquire(execution.selected_provider)
            with semaphore:
                provider_capacity.mark_start(execution.selected_provider)
                log_event(
                    logger,
                    "info",
                    "scheduler.execute",
                    request_id=execution.request_id,
                    provider=execution.selected_provider,
                    queue_wait_ms=queue_wait_ms,
                    lifecycle_state=EXECUTING,
                )

                cached = response_cache.get(execution.prompt)
                if cached is not None:
                    cache_hit = True
                    result = InferenceResult(
                        provider=cached.provider,
                        original_provider=execution.selected_provider,
                        fallback_used=False,
                        model=cached.model,
                        category="cached",
                        response=cached.response,
                        latency_ms=0,
                    )
                    log_event(logger, "info", "cache.hit", request_id=execution.request_id, provider=cached.provider, cache_hit=True)
                else:
                    log_event(logger, "info", "cache.miss", request_id=execution.request_id, provider=execution.selected_provider, cache_hit=False)
                    result = run_inference(
                        prompt=execution.prompt,
                        memory_context=execution.memory_context,
                    )
                    response_cache.put(execution.prompt, result.response, result.provider, result.model)

            execution_duration_ms = round((perf_counter() - started) * 1000)
            mark_request_success(
                db=db,
                request_id=execution.request_id,
                inference_result=result,
                queue_wait_ms=queue_wait_ms,
                execution_duration_ms=execution_duration_ms,
                cache_hit=cache_hit,
            )
            transition_request(db, execution.request_id, COMPLETED)
            provider_capacity.mark_complete(execution.selected_provider, execution_duration_ms)
            self._record_finish(queue_wait_ms, execution_duration_ms, failed=False)
            historical_metrics.record(
                "request_execution",
                {
                    "provider": result.provider,
                    "queue_wait_ms": queue_wait_ms,
                    "execution_duration_ms": execution_duration_ms,
                    "fallback_used": result.fallback_used,
                    "cache_hit": cache_hit,
                    "status": "completed",
                },
            )
            execution.future.set_result(
                {
                    "request_id": execution.request_id,
                    "queue_wait_ms": queue_wait_ms,
                    "execution_duration_ms": execution_duration_ms,
                    "inference_result": result,
                    "cache_hit": cache_hit,
                }
            )
        except ProviderError as exc:
            execution_duration_ms = round((perf_counter() - started) * 1000)
            mark_request_failed(
                db=db,
                request_id=execution.request_id,
                error_message=str(exc),
                queue_wait_ms=queue_wait_ms,
                execution_duration_ms=execution_duration_ms,
            )
            transition_request(db, execution.request_id, FAILED, detail=str(exc))
            provider_capacity.mark_complete(execution.selected_provider, execution_duration_ms, failed=True)
            self._record_finish(queue_wait_ms, execution_duration_ms, failed=True)
            historical_metrics.record(
                "request_execution",
                {
                    "provider": execution.selected_provider,
                    "queue_wait_ms": queue_wait_ms,
                    "execution_duration_ms": execution_duration_ms,
                    "fallback_used": False,
                    "cache_hit": cache_hit,
                    "status": "failed",
                },
            )
            execution.future.set_exception(exc)
        except Exception as exc:
            execution_duration_ms = round((perf_counter() - started) * 1000)
            recovery_registry.record("execution_exception_cleanup", str(exc), request_id=execution.request_id)
            mark_request_failed(
                db=db,
                request_id=execution.request_id,
                error_message=str(exc),
                queue_wait_ms=queue_wait_ms,
                execution_duration_ms=execution_duration_ms,
            )
            transition_request(db, execution.request_id, FAILED, detail=str(exc))
            self._record_finish(queue_wait_ms, execution_duration_ms, failed=True)
            execution.future.set_exception(exc)
        finally:
            with self._lock:
                self._active_executions = max(0, self._active_executions - 1)
                self._queued_request_ids.discard(execution.request_id)
                self._active_request_ids.discard(execution.request_id)
            db.close()

    def _record_finish(self, queue_wait_ms: int, execution_duration_ms: int, failed: bool) -> None:
        with self._lock:
            self._queue_wait_total_ms += queue_wait_ms
            self._execution_total_ms += execution_duration_ms
            if failed:
                self._failed_count += 1
            else:
                self._completed_count += 1


queue_manager = QueueManager()
