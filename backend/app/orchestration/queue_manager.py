import logging
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count
from time import perf_counter

from app.database.session import SessionLocal
from app.orchestration.capacity import provider_capacity
from app.orchestration.lifecycle import COMPLETED, EXECUTING, FAILED, QUEUED, SCHEDULED, transition_request
from app.orchestration.scheduler import priority_weight, select_execution_provider, select_adaptive_provider
from app.providers import ProviderError
from app.services.dedup_tracker import dedup_tracker
from app.services.inference_service import InferenceResult, run_inference
from app.services.request_service import mark_request_success, mark_request_failed
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

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for index in range(settings.max_concurrent_requests):
            thread = threading.Thread(target=self._worker, name=f"qorvexis-worker-{index}", daemon=True)
            thread.start()
        logger.info("queue.start workers=%s", settings.max_concurrent_requests)

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
        execution = QueuedExecution(
            priority_sort=priority_weight(priority),
            sequence=next(self._sequence),
            request_id=request_id,
            prompt=prompt,
            memory_context=memory_context,
            selected_provider=selected_provider,
            queued_at=datetime.now(timezone.utc),
            future=future,
        )
        self._queue.put(execution)
        provider_capacity.mark_queued(selected_provider)
        logger.info(
            "queue.enqueue request_id=%s priority=%s provider=%s depth=%s",
            request_id,
            priority,
            selected_provider,
            self._queue.qsize(),
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
            }

    def _worker(self) -> None:
        while True:
            execution = self._queue.get()
            self._execute(execution)
            self._queue.task_done()

    def _execute(self, execution: QueuedExecution) -> None:
        provider_capacity.mark_dequeued(execution.selected_provider)
        queue_wait_ms = round(
            (datetime.now(timezone.utc) - execution.queued_at).total_seconds() * 1000
        )
        db = SessionLocal()
        started = perf_counter()
        try:
            transition_request(db, execution.request_id, SCHEDULED)
            transition_request(db, execution.request_id, EXECUTING)
            with self._lock:
                self._active_executions += 1
            semaphore = provider_capacity.acquire(execution.selected_provider)
            with semaphore:
                provider_capacity.mark_start(execution.selected_provider)
                logger.info("scheduler.execute request_id=%s provider=%s", execution.request_id, execution.selected_provider)

                # Phase 5 — check response cache before calling provider
                cached = response_cache.get(execution.prompt)
                if cached is not None:
                    result = InferenceResult(
                        provider=cached.provider,
                        original_provider=execution.selected_provider,
                        fallback_used=False,
                        model=cached.model,
                        category="cached",
                        response=cached.response,
                        latency_ms=0,
                    )
                    logger.info("scheduler.cache_hit request_id=%s", execution.request_id)
                else:
                    result = run_inference(
                        prompt=execution.prompt,
                        memory_context=execution.memory_context,
                    )
                    # Phase 5 — store successful response in cache
                    response_cache.put(execution.prompt, result.response, result.provider, result.model)
            execution_duration_ms = round((perf_counter() - started) * 1000)
            mark_request_success(
                db=db,
                request_id=execution.request_id,
                inference_result=result,
                queue_wait_ms=queue_wait_ms,
                execution_duration_ms=execution_duration_ms,
            )
            transition_request(db, execution.request_id, COMPLETED)
            provider_capacity.mark_complete(execution.selected_provider, execution_duration_ms)
            self._record_finish(queue_wait_ms, execution_duration_ms, failed=False)
            execution.future.set_result(
                {
                    "request_id": execution.request_id,
                    "queue_wait_ms": queue_wait_ms,
                    "execution_duration_ms": execution_duration_ms,
                    "inference_result": result,
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
            execution.future.set_exception(exc)
        finally:
            with self._lock:
                self._active_executions = max(0, self._active_executions - 1)
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
