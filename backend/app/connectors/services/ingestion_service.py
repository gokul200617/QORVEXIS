"""IngestionService — orchestrates the connector sync lifecycle."""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.connectors.base.base_connector import BaseConnector
from app.connectors.base.ingestion_result import IngestionResult
from app.connectors.health.connector_health_service import connector_health_service
from app.connectors.models.connector_sync_event import ConnectorSyncEvent
from app.connectors.services.connector_service import connector_service

logger = logging.getLogger("qorvexis.connectors.ingestion")


class IngestionService:
    """Coordinates telemetry ingestion from connectors to the DB."""

    @staticmethod
    def run_sync(db: Session, connector: BaseConnector) -> IngestionResult:
        """Execute a full sync cycle for a single connector."""
        
        logger.info("ingestion.sync_start id=%s", connector.connector_id)

        # 1. Execute the connector's internal sync logic
        result = connector.sync()

        # 2. Update health tracker singleton
        connector_health_service.record_sync(result)

        # 3. Persist audit trail event
        event = ConnectorSyncEvent(
            connector_id=result.connector_id,
            connector_name=result.connector_name,
            success=result.success,
            records_ingested=result.records_ingested,
            duration_ms=result.duration_ms,
            error_message=result.error_message,
        )
        db.add(event)

        # 4. Update the connector instance metadata
        instance = connector_service.get_connector(db, connector.connector_id)
        if instance:
            instance.sync_count += 1
            if result.success:
                instance.last_synced_at = datetime.now(timezone.utc)
            else:
                instance.error_count += 1
                instance.last_error_at = datetime.now(timezone.utc)
            
            # Pull computed status from health service
            health = connector_health_service.get(connector.connector_id)
            if health:
                instance.status = health.status.value

        db.commit()
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────
ingestion_service = IngestionService()
