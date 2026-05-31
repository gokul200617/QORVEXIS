"""Workload signature models."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class WorkloadSignatureRecord(Base):
    __tablename__ = "workload_signatures"
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    signature: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    example_category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
