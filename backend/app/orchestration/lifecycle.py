import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.request_lifecycle_event import RequestLifecycleEvent
from app.models.request_log import RequestLog

logger = logging.getLogger("qorvexis.lifecycle")

QUEUED = "queued"
SCHEDULED = "scheduled"
EXECUTING = "executing"
FALLBACK_EXECUTING = "fallback_executing"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"


def transition_request(
    db: Session,
    request_id: int,
    state: str,
    detail: str | None = None,
) -> None:
    request = db.get(RequestLog, request_id)
    if not request:
        return

    now = datetime.now(timezone.utc)
    request.lifecycle_state = state
    if state == QUEUED and request.queued_at is None:
        request.queued_at = now
    elif state == EXECUTING:
        request.execution_started_at = now
    elif state in {COMPLETED, FAILED, CANCELLED}:
        request.completed_at = now

    db.add(
        RequestLifecycleEvent(
            request_id=request_id,
            state=state,
            detail=detail,
        )
    )
    db.add(request)
    db.commit()
    logger.info("lifecycle.transition request_id=%s state=%s detail=%s", request_id, state, detail)
