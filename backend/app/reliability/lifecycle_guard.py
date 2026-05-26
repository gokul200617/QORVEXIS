import logging

from sqlalchemy.orm import Session

from app.models.request_log import RequestLog
from app.observability.logger import log_event
from app.reliability.integrity import integrity_registry
from app.reliability.state_validator import validate_transition

logger = logging.getLogger("qorvexis.lifecycle_guard")


def validate_lifecycle_transition(
    db: Session,
    request_id: int,
    next_state: str,
    detail: str | None = None,
) -> bool:
    request = db.get(RequestLog, request_id)
    current_state = request.lifecycle_state if request else None
    validation = validate_transition(current_state, next_state)
    if validation.allowed:
        return True

    integrity_registry.record_violation(
        request_id=request_id,
        current_state=current_state,
        attempted_state=next_state,
        reason=validation.reason or "invalid_transition",
        detail=detail,
    )
    log_event(
        logger,
        "warning",
        "lifecycle.violation",
        request_id=request_id,
        current_state=current_state,
        attempted_state=next_state,
        reason=validation.reason,
        detail=detail,
    )
    return False
