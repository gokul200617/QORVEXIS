"""Phase 10A — Provider Usage Snapshot Model.

Stores historical usage ingested directly from the provider API.
"""

from datetime import datetime
from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base
from app.connectors.base.provider_capabilities import ProviderDataSource, ProviderDataConfidence


class ProviderUsageSnapshot(Base):
    """Historical snapshot of provider usage, aggregated daily/monthly."""
    __tablename__ = "provider_usage_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Target date/time for the snapshot (e.g. 2026-05-28 00:00:00 for a daily snapshot)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # Store token counts by model (e.g. {"gpt-4o": 15000, "gpt-3.5-turbo": 5000})
    model_distribution: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # Trust metadata
    source: Mapped[str] = mapped_column(String(32), nullable=False, default=ProviderDataSource.PROVIDER_API.value)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default=ProviderDataConfidence.REAL_PROVIDER_USAGE.value)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
