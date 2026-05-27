"""IngestionResult — the typed return value from every connector sync cycle."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IngestionResult:
    """Carries the outcome of a single connector sync attempt."""

    connector_id:     str
    connector_name:   str
    success:          bool
    records_ingested: int   = 0
    duration_ms:      int   = 0
    error_message:    str | None = None
    normalized_data:  dict  = field(default_factory=dict)
    synced_at:        datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "connector_id":     self.connector_id,
            "connector_name":   self.connector_name,
            "success":          self.success,
            "records_ingested": self.records_ingested,
            "duration_ms":      self.duration_ms,
            "error_message":    self.error_message,
            "synced_at":        self.synced_at.isoformat(),
        }
