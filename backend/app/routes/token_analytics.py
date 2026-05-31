"""Token Intelligence API Endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import require_org
from app.auth.models import UserProfile
from app.database.session import get_db
from app.token_intelligence.analytics import (
    spend_analytics,
    efficiency_engine,
    model_optimization_engine
)

router = APIRouter(prefix="/analytics/token", tags=["token_intelligence"])


@router.get("/spend")
def get_spend_metrics(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return top cost drivers and overall spend summary."""
    try:
        summary = spend_analytics.get_overall_spend_summary(db, org_id=user.organization_id)
        drivers = spend_analytics.get_top_cost_drivers(db, org_id=user.organization_id)
        return {
            "summary": summary,
            "drivers": drivers
        }
    except SQLAlchemyError as exc:
        return {"error": str(exc), "summary": {}, "drivers": {}}


@router.get("/trends")
def get_trend_metrics(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return trend analysis metrics (e.g. top costly workloads, high inflation)."""
    try:
        top_workloads = spend_analytics.get_top_costly_workloads(db, limit=10, org_id=user.organization_id)
        high_inflation = spend_analytics.get_high_inflation_workloads(db, limit=10, org_id=user.organization_id)
        return {
            "top_costly_workloads": top_workloads,
            "high_inflation_workloads": high_inflation
        }
    except SQLAlchemyError as exc:
        return {"error": str(exc), "top_costly_workloads": [], "high_inflation_workloads": []}


@router.get("/efficiency")
def get_efficiency_metrics(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return infrastructure efficiency scores."""
    try:
        return efficiency_engine.compute_efficiency_metrics(db, org_id=user.organization_id)
    except SQLAlchemyError as exc:
        return {"error": str(exc), "efficiency_score": 0.0, "duplicate_workload_pct": 0.0, "cache_opportunity_pct": 0.0}


@router.get("/recommendations")
def get_optimization_recommendations(user: UserProfile = Depends(require_org), db: Session = Depends(get_db)):
    """Return deterministic optimization recommendations."""
    try:
        recs = model_optimization_engine.generate_recommendations(db, org_id=user.organization_id)
        return {"recommendations": recs}
    except SQLAlchemyError as exc:
        return {"error": str(exc), "recommendations": []}
