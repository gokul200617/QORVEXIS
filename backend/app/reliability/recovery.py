import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.observability.logger import log_event
from sqlalchemy import or_

from app.settings import settings

logger = logging.getLogger("qorvexis.recovery")


@dataclass(frozen=True)
class RecoveryAction:
    action: str
    request_id: int | None
    reason: str
    created_at: datetime


class RecoveryRegistry:
    def __init__(self, max_events: int = 500) -> None:
        self._lock = threading.Lock()
        self._actions: deque[RecoveryAction] = deque(maxlen=max_events)

    def record(self, action: str, reason: str, request_id: int | None = None) -> None:
        event = RecoveryAction(
            action=action,
            request_id=request_id,
            reason=reason,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._actions.append(event)
        log_event(logger, "warning", "recovery.action", action=action, request_id=request_id, reason=reason)

    def snapshot(self) -> dict:
        with self._lock:
            actions = list(self._actions)
        return {
            "recovery_action_count": len(actions),
            "recent_actions": [
                {
                    "action": item.action,
                    "request_id": item.request_id,
                    "reason": item.reason,
                    "created_at": item.created_at.isoformat(),
                }
                for item in reversed(actions[-50:])
            ],
        }


recovery_registry = RecoveryRegistry()


def sweep_stale_executions() -> int:
    from app.database.session import SessionLocal
    from app.models.request_log import RequestLog
    from app.orchestration.lifecycle import FAILED, transition_request
    from app.reliability.reconciliation import reconciliation_registry
    from app.services.request_service import mark_request_failed

    db = SessionLocal()
    recovered = 0
    recovered_ids: set[int] = set()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.stale_execution_seconds)
        rows = (
            db.query(RequestLog)
            .filter(RequestLog.lifecycle_state.in_(("scheduled", "executing", "fallback_executing")))
            .filter(
                or_(
                    RequestLog.execution_started_at < cutoff,
                    RequestLog.scheduled_at < cutoff,
                )
            )
            .limit(25)
            .all()
        )
        for row in rows:
            mark_request_failed(
                db=db,
                request_id=row.id,
                error_message="Recovered stale execution after lifecycle timeout.",
                queue_wait_ms=row.queue_wait_ms,
                execution_duration_ms=row.execution_duration_ms,
            )
            transition_request(db, row.id, FAILED, detail="stale_execution_recovery")
            recovery_registry.record("stale_execution_cleanup", "execution exceeded stale threshold", row.id)
            recovered_ids.add(row.id)
            recovered += 1
        reconciliation_registry.reconcile_terminal_requests(recovered_ids, source="recovery_sweeper")
    finally:
        db.close()
    return recovered
