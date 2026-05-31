"""ConnectorService — CRUD operations for connector metadata."""

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.connectors.models.connector_instance import ConnectorInstance
from app.connectors.models.connector_credentials import ConnectorCredentialMetadata
from app.connectors.schemas.connector_schema import ConnectorCreateRequest
from app.connectors.base.connector_status import ConnectorStatus
from app.connectors.registry.connector_registry import connector_registry
from app.connectors.health.connector_health_service import connector_health_service


class ConnectorService:
    """Manages persistence of connector configuration and metadata."""

    @staticmethod
    def create_connector(db: Session, req: ConnectorCreateRequest, org_id: str | None = None) -> ConnectorInstance:
        """Register a new connector instance in the database."""
        
        # 1. Create instance record
        instance = ConnectorInstance(
            connector_id=req.connector_id,
            name=req.name,
            connector_type=req.connector_type.value,
            description=req.description,
            status=ConnectorStatus.DISCONNECTED.value,
            organization_id=org_id,
        )
        db.add(instance)
        
        # 2. Create credential metadata (no raw secrets!)
        creds = ConnectorCredentialMetadata(
            connector_id=req.connector_id,
            auth_type=req.auth_config.auth_type.value,
            safe_reference=req.auth_config.safe_reference,
            masked_identifier=req.auth_config.masked_identifier,
        )
        db.add(creds)
        
        db.commit()
        db.refresh(instance)

        # 3. Initialize health state
        connector_health_service.ensure(instance.connector_id, instance.name)

        return instance

    @staticmethod
    def get_connector(db: Session, connector_id: str) -> ConnectorInstance | None:
        """Fetch a single connector by ID."""
        return db.execute(
            select(ConnectorInstance).where(ConnectorInstance.connector_id == connector_id)
        ).scalar_one_or_none()

    @staticmethod
    def list_connectors(db: Session, org_id: str | None = None) -> list[ConnectorInstance]:
        """Fetch all registered connectors."""
        return list(db.execute(select(ConnectorInstance)).scalars().all())

    @staticmethod
    def update_status(db: Session, connector_id: str, status: ConnectorStatus) -> None:
        """Update the persisted status of a connector."""
        instance = ConnectorService.get_connector(db, connector_id)
        if instance:
            instance.status = status.value
            db.commit()


# ── Singleton ─────────────────────────────────────────────────────────────────
connector_service = ConnectorService()
