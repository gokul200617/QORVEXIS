"""Provider Intelligence API — Phase 9."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from app.database.session import Session, get_db

from app.auth.dependencies import require_org
from app.auth.models import UserProfile

from app.connectors.services.provider_intelligence_service import provider_intelligence_service
from app.connectors.services.provider_optimization_engine import provider_optimization_engine
from app.connectors.services.provider_summary_service import provider_summary_service
from app.connectors.services.provider_visibility_service import provider_visibility_service
from app.connectors.services.provider_usage_sync_service import provider_usage_sync_service

logger = logging.getLogger("qorvexis.routes.providers")

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/summary")
def get_provider_summary(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return the high-level multi-provider dashboard payload."""
    try:
        return provider_summary_service.get_summary(db, org_id=user.organization_id)
    except Exception as exc:
        logger.error("providers.summary.error detail=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch provider summary.")


@router.get("/comparison")
def get_provider_comparison(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return the provider comparison matrix."""
    try:
        return provider_intelligence_service.get_provider_comparison(db, org_id=user.organization_id)
    except Exception as exc:
        logger.error("providers.comparison.error detail=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch provider comparison.")


@router.get("/recommendations")
def get_provider_recommendations(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return optimization and routing recommendations."""
    try:
        return provider_optimization_engine.generate_recommendations(db, org_id=user.organization_id)
    except Exception as exc:
        logger.error("providers.recommendations.error detail=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch provider recommendations.")


@router.get("/workloads")
def get_provider_workloads(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return the workload attribution mapping (spend & latency per signature)."""
    try:
        return provider_optimization_engine.get_workload_attributions(db, org_id=user.organization_id)
    except Exception as exc:
        logger.error("providers.workloads.error detail=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch workload attribution.")


@router.get("/visibility")
def get_provider_visibility(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return the visibility and data source capability report."""
    try:
        return provider_visibility_service.get_visibility_report(db, org_id=user.organization_id)
    except Exception as exc:
        logger.error("providers.visibility.error detail=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch provider visibility.")


@router.post("/sync")
def sync_provider_usage(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Trigger an immediate sync of provider usage."""
    try:
        return provider_usage_sync_service.sync_all(db, org_id=user.organization_id)
    except Exception as exc:
        logger.error("providers.sync.error detail=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to trigger provider usage sync.")
