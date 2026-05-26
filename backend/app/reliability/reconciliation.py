import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.observability.logger import log_event, orchestration_payload

logger = logging.getLogger("qorvexis.reconciliation")


@dataclass(frozen=True)
class ReconciliationEvent:
    request_id: int
    action: str
    source: str
    created_at: datetime


Reconciler = Callable[[set[int], str], dict]


class ReconciliationRegistry:
    def __init__(self, max_events: int = 500) -> None:
        self._lock = threading.Lock()
        self._reconciler: Reconciler | None = None
        self._events: deque[ReconciliationEvent] = deque(maxlen=max_events)
        self._cleanup_count = 0

    def register(self, reconciler: Reconciler) -> None:
        with self._lock:
            self._reconciler = reconciler

    def reconcile_terminal_requests(self, request_ids: set[int], source: str) -> dict:
        with self._lock:
            reconciler = self._reconciler
        if reconciler is None or not request_ids:
            return {"reconciled": 0, "request_ids": [], "source": source}

        result = reconciler(request_ids, source)
        reconciled_ids = [int(request_id) for request_id in result.get("request_ids", [])]
        now = datetime.now(timezone.utc)
        with self._lock:
            for request_id in reconciled_ids:
                self._events.append(
                    ReconciliationEvent(
                        request_id=request_id,
                        action="stale_active_cleanup",
                        source=source,
                        created_at=now,
                    )
                )
            self._cleanup_count += len(reconciled_ids)

        for request_id in reconciled_ids:
            log_event(
                logger,
                "warning",
                "reconciliation.stale_active_cleanup",
                **orchestration_payload(
                    request_id=request_id,
                    lifecycle_state="failed",
                    reconciliation_state="cleaned",
                    source=source,
                ),
            )
        return {
            "reconciled": len(reconciled_ids),
            "request_ids": reconciled_ids,
            "source": source,
        }

    def snapshot(self) -> dict:
        with self._lock:
            events = list(self._events)
            cleanup_count = self._cleanup_count
        return {
            "stale_active_cleanup_count": cleanup_count,
            "recent_reconciliations": [
                {
                    "request_id": item.request_id,
                    "action": item.action,
                    "source": item.source,
                    "created_at": item.created_at.isoformat(),
                }
                for item in reversed(events[-50:])
            ],
        }


reconciliation_registry = ReconciliationRegistry()
