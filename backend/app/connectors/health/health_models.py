"""Connector health state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.connectors.base.connector_status import ConnectorStatus


@dataclass
class ConnectorHealthState:
    """Per-connector operational health snapshot."""

    connector_id:       str
    connector_name:     str
    status:             ConnectorStatus = ConnectorStatus.DISCONNECTED
    validation_passed:  bool            = False
    last_sync_at:       datetime | None = None
    last_error_at:      datetime | None = None
    last_error_message: str | None      = None
    sync_success_count: int             = 0
    sync_failure_count: int             = 0
    consecutive_failures: int           = 0

    @property
    def freshness_seconds(self) -> float | None:
        """Seconds since the last successful sync."""
        if self.last_sync_at is None:
            return None
        delta = datetime.now(timezone.utc) - self.last_sync_at
        return round(delta.total_seconds(), 1)

    @property
    def is_stale(self, threshold_seconds: float = 300.0) -> bool:
        f = self.freshness_seconds
        return f is None or f > threshold_seconds

    def to_dict(self) -> dict:
        return {
            "connector_id":         self.connector_id,
            "connector_name":       self.connector_name,
            "status":               self.status.value,
            "validation_passed":    self.validation_passed,
            "last_sync_at":         self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_error_at":        self.last_error_at.isoformat() if self.last_error_at else None,
            "last_error_message":   self.last_error_message,
            "sync_success_count":   self.sync_success_count,
            "sync_failure_count":   self.sync_failure_count,
            "consecutive_failures": self.consecutive_failures,
            "freshness_seconds":    self.freshness_seconds,
        }
