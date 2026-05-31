import logging
from concurrent.futures import TimeoutError

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import require_org
from app.auth.models import UserProfile
from app.database.session import SessionLocal
from app.observability.logger import log_event
from app.observability.tracing import trace_context
from app.orchestration.queue_manager import queue_manager
from app.orchestration.scheduler import assign_priority
from app.providers import ProviderError
from app.routes.schemas import AskRequest, AskResponse
from app.services.cost_tracker import cost_tracker
from app.services.dedup_tracker import dedup_tracker
from app.services.request_service import create_queued_request
from app.services.session_service import (
    get_or_create_session,
    get_recent_session_context,
    touch_session,
)
from app.settings import settings

router = APIRouter(tags=["requests"])
logger = logging.getLogger("qorvexis.request")


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    user: UserProfile = Depends(require_org),
) -> AskResponse:
    with trace_context(session_id=payload.session_id):
        return _ask_traced(payload, user.organization_id)


def _ask_traced(payload: AskRequest, org_id: str) -> AskResponse:
    log_event(logger, "info", "request.received", prompt_length=len(payload.prompt))
    
    with SessionLocal() as db:
        active_session = get_or_create_session(
            db=db,
            session_id=payload.session_id,
            prompt=payload.prompt,
            org_id=org_id,
        )
        active_session_id = active_session.id
        memory_context = get_recent_session_context(db, active_session_id, org_id=org_id)
        priority = assign_priority(payload.prompt)
        queued_request = create_queued_request(
            db=db,
            session_id=active_session_id,
            prompt=payload.prompt,
            priority=priority,
            org_id=org_id,
        )
        queued_request_id = queued_request.id
        db.commit()

    try:
        future = queue_manager.enqueue(
            request_id=queued_request_id,
            prompt=payload.prompt,
            priority=priority,
            memory_context=memory_context,
            session_id=active_session_id,
            org_id=org_id,  # We may need to pass this to enqueue if the workers need it, but the RequestLog is already tied to org_id. We'll add it if needed later.
        )
        execution = future.result(timeout=settings.request_timeout_seconds)
        inference_result = execution["inference_result"]
    except ProviderError as exc:
        log_event(logger, "error", "request.provider_failure", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TimeoutError as exc:
        log_event(logger, "error", "request.timeout", timeout_seconds=settings.request_timeout_seconds)
        raise HTTPException(status_code=504, detail="Request execution timed out.") from exc

    with SessionLocal() as db:
        try:
            from app.models.inference_session import InferenceSession
            active_session = db.query(InferenceSession).filter(InferenceSession.id == active_session_id).one()
            touch_session(db, active_session)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            message = str(exc.__cause__ or exc)
            log_event(logger, "error", "request.database_failure", error=message)
            raise HTTPException(
                status_code=503,
                detail=f"Database unavailable. Check DATABASE_URL. {message}",
            ) from exc

    is_cache_hit = bool(execution.get("cache_hit", inference_result.category == "cached"))
    is_deduplicated = dedup_tracker.is_duplicate(payload.prompt)
    estimated_cost = (
        cost_tracker.record_request(
            inference_result.provider, payload.prompt, inference_result.response
        )
        if not is_cache_hit
        else 0.0
    )

    # Phase 8C - Emit request telemetry to Token Intelligence Engine
    try:
        from app.token_intelligence.services.token_tracking_service import token_tracking_service
        from app.token_intelligence.schemas.token_schema import TokenTelemetryCreate
        
        prompt_tokens = cost_tracker._estimate_tokens(payload.prompt) if not is_cache_hit else 0
        completion_tokens = cost_tracker._estimate_tokens(inference_result.response) if not is_cache_hit else 0
        
        token_tracking_service.record_telemetry(TokenTelemetryCreate(
            organization_id=org_id,
            provider=inference_result.provider,
            model=inference_result.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost=estimated_cost,
            latency_ms=execution["queue_wait_ms"] + execution["execution_duration_ms"],
            execution_duration_ms=execution["execution_duration_ms"],
            request_category=inference_result.category,
            cache_hit=is_cache_hit,
            fallback_used=inference_result.fallback_used,
            deduplicated=is_deduplicated,
            session_id=str(active_session_id) if active_session_id else None,
            request_id=str(queued_request_id) if queued_request_id else None,
            prompt_text=payload.prompt
        ))
    except Exception as exc:
        log_event(logger, "warning", "token_intelligence.emit_failed", error=str(exc))

    log_event(
        logger,
        "info",
        "request.complete",
        request_id=queued_request_id,
        session_id=active_session_id,
        provider=inference_result.provider,
        original_provider=inference_result.original_provider,
        fallback_used=inference_result.fallback_used,
        category=inference_result.category,
        queue_wait_ms=execution["queue_wait_ms"],
        execution_duration_ms=execution["execution_duration_ms"],
        lifecycle_state="completed",
        cache_hit=is_cache_hit,
        deduplicated=is_deduplicated,
    )
    return AskResponse(
        request_id=queued_request_id,
        session_id=active_session_id,
        provider=inference_result.provider,
        original_provider=inference_result.original_provider,
        fallback_used=inference_result.fallback_used,
        model=inference_result.model,
        category=inference_result.category,
        priority=priority,
        lifecycle_state="completed",
        queue_wait_ms=execution["queue_wait_ms"],
        execution_duration_ms=execution["execution_duration_ms"],
        response=inference_result.response,
        latency_ms=execution["queue_wait_ms"] + execution["execution_duration_ms"],
        cache_hit=is_cache_hit,
        deduplicated=is_deduplicated,
        estimated_cost=round(estimated_cost, 6),
    )
