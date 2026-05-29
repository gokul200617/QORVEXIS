"""Business Intelligence API — Phase 10.

All endpoints are failure-isolated. Business intelligence failures NEVER
affect orchestration, gateway, connectors, or token intelligence.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from app.database.session import Session, get_db

logger = logging.getLogger("qorvexis.routes.business")
router = APIRouter(prefix="/business", tags=["business"])


@router.get("/summary")
def get_business_summary(db: Session = Depends(get_db)):
    """Executive-level KPI summary: spend, top driver, savings opportunity."""
    try:
        from app.business.business_intelligence_service import business_intelligence_service
        return business_intelligence_service.get_summary(db)
    except Exception as exc:
        logger.error("business.summary.error detail=%s", exc)
        return {
            "total_ai_spend": 0.0,
            "gateway_spend": 0.0,
            "gateway_requests": 0,
            "top_cost_driver": "No data",
            "top_team": "No data",
            "top_customer": "No data",
            "optimization_opportunity": 0.0,
            "workload_count": 0,
            "team_count": 0,
            "customer_count": 0,
        }


@router.get("/workloads")
def get_business_workloads(db: Session = Depends(get_db)):
    """Returns all workloads ranked by spend."""
    try:
        from app.business.business_intelligence_service import business_intelligence_service
        return business_intelligence_service.get_workloads(db)
    except Exception as exc:
        logger.error("business.workloads.error detail=%s", exc)
        return []


@router.get("/teams")
def get_business_teams(db: Session = Depends(get_db)):
    """Returns team attribution: cost, tokens, optimization score."""
    try:
        from app.business.business_intelligence_service import business_intelligence_service
        return business_intelligence_service.get_teams(db)
    except Exception as exc:
        logger.error("business.teams.error detail=%s", exc)
        return []


@router.get("/customers")
def get_business_customers(db: Session = Depends(get_db)):
    """Returns customer attribution: cost, requests, tokens."""
    try:
        from app.business.business_intelligence_service import business_intelligence_service
        return business_intelligence_service.get_customers(db)
    except Exception as exc:
        logger.error("business.customers.error detail=%s", exc)
        return []


@router.get("/forecast")
def get_business_forecast(db: Session = Depends(get_db)):
    """Returns 7, 30, 90-day spend forecasts based on historical trend."""
    try:
        from app.business.forecasting_engine import forecasting_engine
        return forecasting_engine.get_forecast(db)
    except Exception as exc:
        logger.error("business.forecast.error detail=%s", exc)
        return {
            "forecast_7d": 0.0, "forecast_30d": 0.0, "forecast_90d": 0.0,
            "trend_direction": "stable", "confidence": "low",
        }


@router.get("/recommendations")
def get_business_recommendations(db: Session = Depends(get_db)):
    """Returns prioritized, actionable optimization recommendations with savings estimates."""
    try:
        from app.business.optimization_engine_v2 import optimization_engine_v2
        return optimization_engine_v2.get_recommendations(db)
    except Exception as exc:
        logger.error("business.recommendations.error detail=%s", exc)
        return []
