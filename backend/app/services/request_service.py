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
    org_id: str | None = None,
) -> RequestLog:
    request_log = RequestLog(
        organization_id=org_id,
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
        received_at=datetime.now(timezone.utc),
        queued_at=datetime.now(timezone.utc),
    )

    db.add(request_log)
    db.commit()
    db.refresh(request_log)
    db.add(
        RequestLifecycleEvent(
            organization_id=org_id,
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
    cache_hit: bool = False,
    org_id: str | None = None,
) -> None:
    q = db.query(RequestLog).filter(RequestLog.id == request_id)
    if org_id:
        q = q.filter(RequestLog.organization_id == org_id)
        
    request_log = q.first()
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
    request_log.provider_response_at = datetime.now(timezone.utc)
    request_log.cache_hit = cache_hit
    db.add(request_log)
    
    db.add(
        RequestLifecycleEvent(
            organization_id=org_id,
            request_id=request_log.id,
            state="success",
        )
    )
    db.commit()


def mark_request_failed(
    db: Session,
    request_id: int,
    error_message: str,
    queue_wait_ms: int | None = None,
    execution_duration_ms: int | None = None,
    org_id: str | None = None,
) -> None:
    q = db.query(RequestLog).filter(RequestLog.id == request_id)
    if org_id:
        q = q.filter(RequestLog.organization_id == org_id)
        
    request_log = q.first()
    if not request_log:
        return

    request_log.request_status = "provider_failure"
    request_log.error_message = error_message
    request_log.queue_wait_ms = queue_wait_ms
    request_log.execution_duration_ms = execution_duration_ms
    db.add(request_log)
    
    db.add(
        RequestLifecycleEvent(
            organization_id=org_id,
            request_id=request_log.id,
            state="failed",
            detail=error_message,
        )
    )
    db.commit()


def record_failed_prompt_request(
    db: Session,
    session_id: str | None,
    prompt: str,
    error_message: str,
    request_status: str = "provider_failure",
    org_id: str | None = None,
) -> None:
    request_log = RequestLog(
        organization_id=org_id,
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
