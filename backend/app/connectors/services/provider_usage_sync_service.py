"""Phase 10A — Provider Usage Sync Service.

Iterates through all registered connectors, evaluates capabilities,
and performs usage ingestion when supported. Records limitations when unsupported.
Ensures ABSOLUTE failure isolation.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.connectors.registry.connector_registry import connector_registry
from app.connectors.base.provider_capabilities import get_capabilities_for_provider
from app.connectors.openai.openai_usage_ingestion_service import openai_usage_ingestion_service
from app.settings import settings

logger = logging.getLogger("qorvexis.connectors.sync")


class ProviderUsageSyncService:
    def __init__(self):
        self.last_sync: datetime | None = None
        self.sync_status: str = "idle"
        self.records_ingested: int = 0
        self.sync_errors: int = 0
        self.sync_duration_ms: float = 0.0

    def sync_all(self, db: Session, org_id: str | None = None) -> dict:
        """Synchronizes usage across all capable connected providers."""
        if self.sync_status == "running":
            return self.get_status()

        self.sync_status = "running"
        logger.info("sync.started")
        t_start = time.monotonic()
        errors_this_run = 0
        ingested_this_run = 0

        try:
            connectors = connector_registry.list_all()
            for c in connectors:
                provider_name = c.connector_id.split("-")[0].lower()
                caps = get_capabilities_for_provider(provider_name)

                if not caps.supports_usage_retrieval:
                    # Explicitly log limitation; do nothing
                    logger.debug("sync.skip provider=%s reason=unsupported", provider_name)
                    continue
                
                # If simulation mode is active and we shouldn't hit real APIs
                if c.simulation_mode:
                    logger.debug("sync.skip provider=%s reason=simulation_mode", provider_name)
                    continue

                try:
                    logger.info("sync.provider.begin provider=%s", provider_name)
                    if provider_name == "openai":
                        # Fetch yesterday's data to ensure complete day sync
                        snapshot = openai_usage_ingestion_service.ingest_daily_usage(db, c.api_key)
                        ingested_this_run += 1
                        logger.info("sync.provider.complete provider=%s records_added=1 cost=%.4f", provider_name, snapshot.estimated_cost)
                except Exception as exc:
                    # Strict failure isolation
                    errors_this_run += 1
                    logger.error("sync.provider.failed provider=%s error=%s", provider_name, exc)

            self.last_sync = datetime.now(timezone.utc)
            self.records_ingested += ingested_this_run
            self.sync_errors += errors_this_run
            self.sync_status = "idle"
            logger.info("sync.finished duration_ms=%.2f errors=%d ingested=%d", (time.monotonic() - t_start)*1000, errors_this_run, ingested_this_run)

        except Exception as exc:
            logger.critical("sync.fatal error=%s", exc)
            self.sync_status = "error"
            self.sync_errors += 1
        finally:
            self.sync_duration_ms = (time.monotonic() - t_start) * 1000

        return self.get_status()

    def get_status(self) -> dict:
        return {
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "sync_status": self.sync_status,
            "records_ingested": self.records_ingested,
            "sync_errors": self.sync_errors,
            "sync_duration_ms": self.sync_duration_ms,
        }


provider_usage_sync_service = ProviderUsageSyncService()
