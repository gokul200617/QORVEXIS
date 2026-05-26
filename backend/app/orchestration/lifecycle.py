import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.request_lifecycle_event import RequestLifecycleEvent
from app.models.request_log import RequestLog
from app.observability.logger import log_event
from app.reliability.lifecycle_guard import validate_lifecycle_transition

logger = logging.getLogger("qorvexis.lifecycle")

RECEIVED = "received"
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
) -> bool:
    request = db.get(RequestLog, request_id)
    if not request:
        return False
    if not validate_lifecycle_transition(db, request_id, state, detail):
        return False

    now = datetime.now(timezone.utc)
    request.lifecycle_state = state
    if state == RECEIVED and request.received_at is None:
        request.received_at = now
    elif state == QUEUED and request.queued_at is None:
        request.queued_at = now
    elif state == SCHEDULED:
        request.scheduled_at = now
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
    log_event(logger, "info", "lifecycle.transition", request_id=request_id, lifecycle_state=state, detail=detail)
    return True
