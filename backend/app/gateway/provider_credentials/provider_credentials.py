from datetime import datetime
import uuid
from sqlalchemy import Column, String, DateTime, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class ProviderCredential(Base):
    """Stores API keys for the Gateway securely."""
    __tablename__ = "provider_credentials"
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    encrypted_key: Mapped[str] = mapped_column(String(512), nullable=False) # In production this would be encrypted
    masked_key: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
