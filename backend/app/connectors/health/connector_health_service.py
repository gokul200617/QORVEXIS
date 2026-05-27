"""ConnectorHealthService — thread-safe in-memory health tracker.

Records sync outcomes per connector and exposes a snapshot for the
dashboard and metrics API.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.connectors.base.connector_status import ConnectorStatus
from app.connectors.base.ingestion_result import IngestionResult
from app.connectors.health.health_models import ConnectorHealthState

logger = logging.getLogger("qorvexis.connectors.health")


class ConnectorHealthService:
    """Tracks health state for all registered connectors."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, ConnectorHealthState] = {}

    # ── Initialisation ────────────────────────────────────────────────────────

    def ensure(self, connector_id: str, connector_name: str) -> None:
        """Create a health state entry if it does not exist yet."""
        with self._lock:
            if connector_id not in self._states:
                self._states[connector_id] = ConnectorHealthState(
                    connector_id=connector_id,
                    connector_name=connector_name,
                )

    # ── Sync outcome recording ────────────────────────────────────────────────

    def record_sync(self, result: IngestionResult) -> None:
        """Update health state based on an IngestionResult."""
        with self._lock:
            state = self._states.setdefault(
                result.connector_id,
                ConnectorHealthState(
                    connector_id=result.connector_id,
                    connector_name=result.connector_name,
                ),
            )

            if result.success:
                state.sync_success_count   += 1
                state.consecutive_failures  = 0
                state.last_sync_at          = datetime.now(timezone.utc)
                state.status                = ConnectorStatus.CONNECTED
                logger.info("health.sync_success id=%s", result.connector_id)
            else:
                state.sync_failure_count   += 1
                state.consecutive_failures += 1
                state.last_error_at         = datetime.now(timezone.utc)
                state.last_error_message    = result.error_message
                state.status = (
                    ConnectorStatus.ERROR
                    if state.consecutive_failures >= 3
                    else ConnectorStatus.DEGRADED
                )
                logger.warning(
                    "health.sync_failure id=%s consecutive=%s error=%s",
                    result.connector_id,
                    state.consecutive_failures,
                    result.error_message,
                )

    def record_validation(self, connector_id: str, passed: bool) -> None:
        """Record the result of a validation attempt."""
        with self._lock:
            state = self._states.get(connector_id)
            if state is None:
                return
            state.validation_passed = passed
            if not passed:
                state.status = ConnectorStatus.ERROR

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, connector_id: str) -> ConnectorHealthState | None:
        with self._lock:
            return self._states.get(connector_id)

    def snapshot(self) -> dict:
        with self._lock:
            states = list(self._states.values())

        return {
            "total":      len(states),
            "connected":  sum(1 for s in states if s.status == ConnectorStatus.CONNECTED),
            "degraded":   sum(1 for s in states if s.status == ConnectorStatus.DEGRADED),
            "error":      sum(1 for s in states if s.status == ConnectorStatus.ERROR),
            "connectors": [s.to_dict() for s in states],
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
connector_health_service = ConnectorHealthService()
