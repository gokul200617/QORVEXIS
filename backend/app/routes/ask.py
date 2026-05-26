import logging
from concurrent.futures import TimeoutError

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.orchestration.queue_manager import queue_manager
from app.orchestration.scheduler import assign_priority
from app.providers import ProviderError
from app.routes.schemas import AskRequest, AskResponse
from app.services.cost_tracker import cost_tracker
from app.services.dedup_tracker import dedup_tracker
from app.services.request_service import create_queued_request
from app.services.response_cache import response_cache
from app.services.session_service import (
    get_or_create_session,
    get_recent_session_context,
    touch_session,
)

router = APIRouter(tags=["requests"])
logger = logging.getLogger("qorvexis.request")


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    logger.info("request.received prompt_length=%s", len(payload.prompt))
    active_session = get_or_create_session(
        db=db,
        session_id=payload.session_id,
        prompt=payload.prompt,
    )
    memory_context = get_recent_session_context(db, active_session.id)
    priority = assign_priority(payload.prompt)
    queued_request = create_queued_request(
        db=db,
        session_id=active_session.id,
        prompt=payload.prompt,
        priority=priority,
    )

    try:
        future = queue_manager.enqueue(
            request_id=queued_request.id,
            prompt=payload.prompt,
            priority=priority,
            memory_context=memory_context,
        )
        execution = future.result(timeout=120)
        inference_result = execution["inference_result"]
    except ProviderError as exc:
        logger.error("request.provider_failure error=%s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Request execution timed out.") from exc

    try:
        touch_session(db, active_session)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        message = str(exc.__cause__ or exc)
        logger.error("request.database_failure error=%s", message)
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable. Check DATABASE_URL. {message}",
        ) from exc

    # Phase 5 — detect cache hit and dedup status
    is_cache_hit = inference_result.category == "cached"
    is_deduplicated = dedup_tracker.is_duplicate(payload.prompt)
    estimated_cost = (
        cost_tracker.record_request(
            inference_result.provider, payload.prompt, inference_result.response
        )
        if not is_cache_hit
        else 0.0
    )

    logger.info(
        "request.complete provider=%s original_provider=%s fallback_used=%s category=%s latency_ms=%s cache_hit=%s dedup=%s",
        inference_result.provider,
        inference_result.original_provider,
        inference_result.fallback_used,
        inference_result.category,
        inference_result.latency_ms,
        is_cache_hit,
        is_deduplicated,
    )
    return AskResponse(
        request_id=queued_request.id,
        session_id=active_session.id,
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
