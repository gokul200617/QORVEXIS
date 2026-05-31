"""TelemetrySnapshotRecord — rate-limited persistence of infrastructure snapshots."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class TelemetrySnapshotRecord(Base):
    __tablename__ = "telemetry_snapshots"

    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="local")
    host_identifier: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # System metrics
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    # GPU metrics
    gpu_available: Mapped[bool] = mapped_column(Boolean, server_default="false")
    gpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Indexed for time-range queries
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
