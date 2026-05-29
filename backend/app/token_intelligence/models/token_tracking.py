"""Token telemetry and snapshot models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class TokenTelemetryRecord(Base):
    __tablename__ = "token_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    execution_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    request_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deduplicated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    workload_signature: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    
    # Store inflation ratio natively for easy analytics
    completion_inflation_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


class TokenSnapshotRecord(Base):
    __tablename__ = "token_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resolution: Mapped[str] = mapped_column(String(16), nullable=False) # e.g. "hourly", "daily"
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    total_spend: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    efficiency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_workload_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_opportunity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
