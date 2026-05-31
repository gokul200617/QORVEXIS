"""ConnectorSyncEvent — append-only log of every sync attempt."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ConnectorSyncEvent(Base):
    """Immutable audit record for each connector sync cycle."""

    __tablename__ = "connector_sync_events"
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connector_id:     Mapped[str]  = mapped_column(String(128), nullable=False, index=True)
    connector_name:   Mapped[str]  = mapped_column(String(128), nullable=False)
    success:          Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    records_ingested: Mapped[int]  = mapped_column(Integer, nullable=False, server_default="0")
    duration_ms:      Mapped[int]  = mapped_column(Integer, nullable=False, server_default="0")
    error_message:    Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
