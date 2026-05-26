from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.request_lifecycle_event import RequestLifecycleEvent
from app.models.request_log import RequestLog
from app.services.inference_service import InferenceResult, classify_request, select_provider_name


def create_queued_request(
    db: Session,
    session_id: str,
    prompt: str,
    priority: str,
) -> RequestLog:
    request_log = RequestLog(
        session_id=session_id,
        prompt=prompt,
        response="",
        provider_used=None,
        original_provider=select_provider_name(prompt),
        fallback_used=False,
        model_used=None,
        latency_ms=None,
        request_category=classify_request(prompt),
        request_priority=priority,
        request_status="queued",
        lifecycle_state="queued",
        queued_at=datetime.now(timezone.utc),
    )

    db.add(request_log)
    db.commit()
    db.refresh(request_log)
    db.add(
        RequestLifecycleEvent(
            request_id=request_log.id,
            state="queued",
            detail=f"priority={priority}",
        )
    )
    db.commit()
    return request_log


def mark_request_success(
    db: Session,
    request_id: int,
    inference_result: InferenceResult,
    queue_wait_ms: int,
    execution_duration_ms: int,
) -> None:
    request_log = db.get(RequestLog, request_id)
    if not request_log:
        return

    request_log.response = inference_result.response
    request_log.provider_used = inference_result.provider
    request_log.original_provider = inference_result.original_provider
    request_log.fallback_used = inference_result.fallback_used
    request_log.model_used = inference_result.model
    request_log.latency_ms = queue_wait_ms + execution_duration_ms
    request_log.request_category = inference_result.category
    request_log.request_status = "success"
    request_log.queue_wait_ms = queue_wait_ms
    request_log.execution_duration_ms = execution_duration_ms
    db.add(request_log)
    db.commit()


def mark_request_failed(
    db: Session,
    request_id: int,
    error_message: str,
    queue_wait_ms: int | None = None,
    execution_duration_ms: int | None = None,
) -> None:
    request_log = db.get(RequestLog, request_id)
    if not request_log:
        return

    request_log.request_status = "provider_failure"
    request_log.error_message = error_message
    request_log.queue_wait_ms = queue_wait_ms
    request_log.execution_duration_ms = execution_duration_ms
    db.add(request_log)
    db.commit()


def record_failed_prompt_request(
    db: Session,
    session_id: str | None,
    prompt: str,
    error_message: str,
    request_status: str = "provider_failure",
) -> None:
    request_log = RequestLog(
        session_id=session_id,
        prompt=prompt,
        response="",
        provider_used=None,
        original_provider=select_provider_name(prompt),
        fallback_used=False,
        model_used=None,
        latency_ms=None,
        request_category=classify_request(prompt),
        request_priority="normal",
        request_status=request_status,
        lifecycle_state="failed",
        error_message=error_message,
    )

    db.add(request_log)
    db.commit()
