"""Connector API Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field

from app.connectors.base.connector_status import ConnectorStatus
from app.connectors.base.connector_types import ConnectorType
from app.connectors.schemas.auth_schema import AuthConfigSchema


class ConnectorCreateRequest(BaseModel):
    """Payload for registering a new connector."""
    connector_id:   str = Field(..., max_length=128, description="Unique string slug, e.g. 'openai-prod'")
    name:           str = Field(..., max_length=128, description="Display name")
    connector_type: ConnectorType
    description:    str | None = None
    auth_config:    AuthConfigSchema = Field(default_factory=AuthConfigSchema)


class ConnectorResponse(BaseModel):
    """Standard API representation of a registered connector."""
    id:             int
    connector_id:   str
    name:           str
    connector_type: ConnectorType
    status:         ConnectorStatus
    description:    str | None
    sync_count:     int
    error_count:    int
    last_synced_at: datetime | None
    last_error_at:  datetime | None
    created_at:     datetime

    class Config:
        from_attributes = True


class ConnectorListResponse(BaseModel):
    total: int
    connectors: list[ConnectorResponse]
