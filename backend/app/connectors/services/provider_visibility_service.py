"""Phase 10A — Provider Visibility Service.

Provides a unified payload to the dashboard explaining data visibility,
source, limitations, and confidence per provider.
"""

from __future__ import annotations
import logging
from sqlalchemy.orm import Session

from app.connectors.registry.connector_registry import connector_registry
from app.connectors.base.provider_capabilities import get_capabilities_for_provider
from app.connectors.services.provider_usage_sync_service import provider_usage_sync_service

logger = logging.getLogger("qorvexis.connectors.visibility")


class ProviderVisibilityService:
    def get_visibility_report(self, db: Session, org_id: str | None = None) -> dict:
        """Returns the visibility status for all connected providers."""
        connectors = connector_registry.list_all()
        
        report = {
            "sync_status": provider_usage_sync_service.get_status(),
            "providers": []
        }

        for c in connectors:
            # The connector ID format is generally {provider}-{timestamp}
            provider_name = c.connector_id.split("-")[0].lower()
            caps = get_capabilities_for_provider(provider_name)
            
            if caps.supports_usage_retrieval:
                visibility_pct = 100
                source = "Provider API"
                confidence = "Real Provider Usage"
                limitation = None
            else:
                visibility_pct = 0
                source = "Gateway Only"
                confidence = "Real Gateway Usage"
                limitation = "Provider Usage API unavailable"
            
            if c.simulation_mode:
                source = "Simulation"
                confidence = "Simulation"
                limitation = "Production telemetry disabled in simulation mode"

            # Query database for records and last sync time
            from app.connectors.models.provider_usage_snapshot import ProviderUsageSnapshot
            from sqlalchemy import func
            
            records_count = db.query(func.count(ProviderUsageSnapshot.id)).filter(
                ProviderUsageSnapshot.provider == provider_name
            ).scalar() or 0
            
            last_sync_record = db.query(ProviderUsageSnapshot.timestamp).filter(
                ProviderUsageSnapshot.provider == provider_name
            ).order_by(ProviderUsageSnapshot.timestamp.desc()).first()
            
            last_sync_iso = last_sync_record[0].isoformat() if last_sync_record else None

            report["providers"].append({
                "provider": provider_name.capitalize(),
                "connector_id": c.connector_id,
                "visibility_pct": visibility_pct,
                "source": source,
                "confidence": confidence,
                "limitation": limitation,
                "simulation_mode": c.simulation_mode,
                "records": records_count,
                "last_sync": last_sync_iso,
            })

        return report


provider_visibility_service = ProviderVisibilityService()
