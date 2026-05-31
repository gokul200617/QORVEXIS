"""TelemetryProvider singleton — in-memory telemetry with rate-limited DB persistence."""

import logging
from time import monotonic
from typing import TYPE_CHECKING

from app.telemetry.normalizers.normalizer import telemetry_normalizer
from app.telemetry.normalizers.schema import TelemetrySnapshot

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("qorvexis.telemetry.provider")


class TelemetryProvider:
    """On-demand telemetry collection with in-memory caching.

    Persistence strategy:
    - Writes to DB at most once per telemetry_persist_interval_seconds (default 300s)
    - Always persists when an anomaly is detected (CPU > threshold or RAM > threshold)
    - DB write failure is caught and logged — never propagated
    """

    def __init__(self) -> None:
        self._last_snapshot: TelemetrySnapshot | None = None
        self._last_persist_monotonic: float = 0.0

    def get_snapshot(self, db: "Session | None" = None, org_id: str | None = None) -> TelemetrySnapshot:
        """Collect a fresh snapshot and optionally persist it."""
        from app.settings import settings

        snapshot = telemetry_normalizer.collect_and_normalize()
        self._last_snapshot = snapshot

        if db is not None and settings.telemetry_persist_snapshots:
            if self._should_persist(snapshot, settings):
                self._persist(snapshot, db, settings, org_id=org_id)

        return snapshot

    def get_latest(self) -> TelemetrySnapshot | None:
        """Return cached snapshot without triggering a new collection."""
        return self._last_snapshot

    def _should_persist(self, snapshot: TelemetrySnapshot, settings) -> bool:
        now = monotonic()
        interval = settings.telemetry_persist_interval_seconds
        elapsed = now - self._last_persist_monotonic

        if elapsed >= interval:
            return True

        # Anomaly triggers immediate persist
        if snapshot.cpu_percent is not None and snapshot.cpu_percent > settings.telemetry_cpu_high_threshold:
            logger.info("telemetry.anomaly_persist cpu_percent=%.1f", snapshot.cpu_percent)
            return True
        if snapshot.memory_percent is not None and snapshot.memory_percent > settings.telemetry_ram_high_threshold:
            logger.info("telemetry.anomaly_persist memory_percent=%.1f", snapshot.memory_percent)
            return True

        return False

    def _persist(self, snapshot: TelemetrySnapshot, db: "Session", settings, org_id: str | None = None) -> None:
        try:
            from app.models.telemetry_snapshot import TelemetrySnapshotRecord

            record = TelemetrySnapshotRecord(
                organization_id=org_id,
                source=snapshot.source,
                cpu_percent=snapshot.cpu_percent,
                memory_percent=snapshot.memory_percent,
                disk_percent=snapshot.disk_percent,
                gpu_percent=snapshot.gpu_percent,
                gpu_memory_percent=snapshot.gpu_memory_percent,
                gpu_available=snapshot.gpu_available,
                host_identifier=snapshot.host_identifier,
            )
            db.add(record)
            db.commit()
            self._last_persist_monotonic = monotonic()
            logger.debug("telemetry.persisted snapshot")
        except Exception as exc:
            logger.warning("telemetry.persist_failed error=%s", exc)
            try:
                db.rollback()
            except Exception:
                pass


telemetry_provider = TelemetryProvider()
