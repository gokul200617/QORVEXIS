import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class IntegrityViolation:
    request_id: int | None
    current_state: str | None
    attempted_state: str
    reason: str
    detail: str | None
    created_at: datetime


class IntegrityRegistry:
    def __init__(self, max_events: int = 500) -> None:
        self._lock = threading.Lock()
        self._violations: deque[IntegrityViolation] = deque(maxlen=max_events)

    def record_violation(
        self,
        request_id: int | None,
        current_state: str | None,
        attempted_state: str,
        reason: str,
        detail: str | None = None,
    ) -> None:
        violation = IntegrityViolation(
            request_id=request_id,
            current_state=current_state,
            attempted_state=attempted_state,
            reason=reason,
            detail=detail,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._violations.append(violation)

    def snapshot(self) -> dict:
        with self._lock:
            violations = list(self._violations)
        return {
            "violation_count": len(violations),
            "recent_violations": [
                {
                    "request_id": item.request_id,
                    "current_state": item.current_state,
                    "attempted_state": item.attempted_state,
                    "reason": item.reason,
                    "detail": item.detail,
                    "created_at": item.created_at.isoformat(),
                }
                for item in reversed(violations[-50:])
            ],
        }


integrity_registry = IntegrityRegistry()

