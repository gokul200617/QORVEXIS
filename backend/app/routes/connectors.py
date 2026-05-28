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


# ── OpenAI Specific Endpoints ──────────────────────────────────────────────────

from datetime import datetime
from pydantic import BaseModel

class OpenAIAccountRequest(BaseModel):
    api_key: str
    name: str = "OpenAI Production"

@router.post("/openai/authenticate", response_model=ConnectorResponse)
def authenticate_openai(req: OpenAIAccountRequest, db: Session = Depends(get_db)):
    """Authenticate and register a new OpenAI connector."""
    
    from app.connectors.openai.openai_connector import OpenAIConnector
    from app.connectors.schemas.connector_schema import ConnectorCreateRequest, AuthConfigSchema
    from app.connectors.schemas.auth_schema import AuthType
    from app.connectors.services.connector_validation_service import connector_validation_service
    from app.connectors.services.ingestion_service import ingestion_service
    from app.connectors.base.connector_types import ConnectorType

    connector_id = f"openai-{int(datetime.now().timestamp())}"
    
    # 1. Instantiate the connector in-memory
    connector = OpenAIConnector(
        connector_id=connector_id,
        name=req.name,
        api_key=req.api_key
    )
    
    # 2. Validate the key safely
    passed = connector_validation_service.validate(connector)
    if not passed:
        raise HTTPException(status_code=401, detail="Invalid OpenAI API Key")
        
    # 3. Register it with the central framework
    connector_registry.register(connector)
    
    # 4. Create metadata in the DB (masked key only)
    masked = f"sk-...{req.api_key[-4:]}" if len(req.api_key) > 4 else "sk-...xxxx"
    
    create_req = ConnectorCreateRequest(
        connector_id=connector_id,
        name=req.name,
        connector_type=ConnectorType.AI_PROVIDER,
        description="Auto-registered OpenAI connection",
        auth_config=AuthConfigSchema(
            auth_type=AuthType.API_KEY,
            masked_identifier=masked
        )
    )
    
    instance = connector_service.create_connector(db, create_req)
    
    # 5. Trigger initial ingestion sync
    ingestion_service.run_sync(db, connector)
    
    return instance

@router.get("/openai/usage")
def get_openai_usage():
    """Return aggregated token analytics for the dashboard."""
    from app.connectors.openai.openai_usage_service import openai_usage_service
    return openai_usage_service.get_analytics_summary()
