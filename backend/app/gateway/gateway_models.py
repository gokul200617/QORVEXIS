"""Phase 10 — Business Attribution DB Models.

GatewayRequestRecord: Full telemetry row captured for every request proxied
through the Qorvexis AI Gateway. This is the primary source of truth for
business intelligence (team, customer, workload attribution).
"""

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class GatewayRequestRecord(Base):
    """Every request proxied through the Qorvexis Gateway generates one row."""
    __tablename__ = "gateway_requests"
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Attribution dimensions — the core of Phase 10
    workload_id:   Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    workload_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    team_id:       Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    team_name:     Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_id:   Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Provider telemetry
    provider:           Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model:              Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    prompt_tokens:      Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens:       Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost:     Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms:         Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Request tracking
    session_id:  Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id:  Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    success:     Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cache_hit:   Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
