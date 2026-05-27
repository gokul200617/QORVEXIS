"""Metrics API extensions for connector management."""

from fastapi import APIRouter, Depends, HTTPException

from app.database.session import get_db, Session
from app.connectors.services.connector_service import connector_service
from app.connectors.registry.connector_registry import connector_registry
from app.connectors.health.connector_health_service import connector_health_service
from app.connectors.schemas.connector_schema import ConnectorResponse, ConnectorListResponse

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorResponse])
def list_connectors(db: Session = Depends(get_db)):
    """Return all persisted connector instances."""
    return connector_service.list_connectors(db)


@router.get("/health")
def get_connectors_health():
    """Return in-memory health snapshots for all connectors."""
    return connector_health_service.snapshot()


@router.get("/status")
def get_connectors_status():
    """Return high-level connector registry status."""
    return connector_registry.snapshot()


@router.get("/{connector_id}", response_model=ConnectorResponse)
def get_connector(connector_id: str, db: Session = Depends(get_db)):
    """Return details for a specific connector."""
    instance = connector_service.get_connector(db, connector_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Connector not found")
    return instance
