"""ConnectorInstance — persisted record of a configured connector."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ConnectorInstance(Base):
    """Represents a configured connector registered with Qorvexis.

    One row per connector (e.g. 'openai-prod', 'aws-us-east-1').
    Credentials are NEVER stored here — only safe metadata.
    """

    __tablename__ = "connector_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connector_id:   Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name:           Mapped[str] = mapped_column(String(128), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(64),  nullable=False)
    status:         Mapped[str] = mapped_column(String(32),  nullable=False, server_default="disconnected")
    description:    Mapped[str | None] = mapped_column(String(512), nullable=True)

    sync_count:  Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    last_synced_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
