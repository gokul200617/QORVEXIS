"""Spend Analytics Engine.

Provides queries for spend trends, most expensive workloads, 
top cost drivers, and high inflation workloads.
"""

from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
from app.token_intelligence.models.workload_signature import WorkloadSignatureRecord


def get_top_costly_workloads(db: Session, limit: int = 5) -> List[Dict[str, Any]]:
    """Get the most expensive repeated workloads by signature."""
    results = db.query(
        TokenTelemetryRecord.workload_signature,
        func.sum(TokenTelemetryRecord.estimated_cost).label("total_cost"),
        func.count(TokenTelemetryRecord.id).label("request_count"),
        func.max(WorkloadSignatureRecord.example_category).label("category")
    ).outerjoin(
        WorkloadSignatureRecord, 
        TokenTelemetryRecord.workload_signature == WorkloadSignatureRecord.signature
    ).filter(
        TokenTelemetryRecord.workload_signature.isnot(None)
    ).group_by(
        TokenTelemetryRecord.workload_signature
    ).order_by(
        desc("total_cost")
    ).limit(limit).all()

    return [
        {
            "signature": row.workload_signature,
            "total_cost_usd": round(row.total_cost, 4),
            "request_count": row.request_count,
            "category": row.category or "unknown"
        }
        for row in results
    ]


def get_top_cost_drivers(db: Session) -> Dict[str, List[Dict[str, Any]]]:
    """Break down costs by model and category."""
    
    by_model = db.query(
        TokenTelemetryRecord.model,
        func.sum(TokenTelemetryRecord.estimated_cost).label("cost")
    ).group_by(TokenTelemetryRecord.model).order_by(desc("cost")).all()
    
    by_category = db.query(
        TokenTelemetryRecord.request_category,
        func.sum(TokenTelemetryRecord.estimated_cost).label("cost")
    ).group_by(TokenTelemetryRecord.request_category).order_by(desc("cost")).all()
    
    return {
        "models": [{"model": r.model, "cost_usd": round(r.cost, 4)} for r in by_model],
        "categories": [{"category": r.request_category or "unknown", "cost_usd": round(r.cost, 4)} for r in by_category]
    }


def get_high_inflation_workloads(db: Session, limit: int = 5) -> List[Dict[str, Any]]:
    """Find workloads with the highest completion inflation ratio."""
    results = db.query(
        TokenTelemetryRecord.workload_signature,
        func.avg(TokenTelemetryRecord.completion_inflation_ratio).label("avg_inflation"),
        func.count(TokenTelemetryRecord.id).label("count"),
        func.max(WorkloadSignatureRecord.example_category).label("category")
    ).outerjoin(
        WorkloadSignatureRecord, 
        TokenTelemetryRecord.workload_signature == WorkloadSignatureRecord.signature
    ).filter(
        TokenTelemetryRecord.workload_signature.isnot(None),
        TokenTelemetryRecord.completion_inflation_ratio > 2.0
    ).group_by(
        TokenTelemetryRecord.workload_signature
    ).having(
        func.count(TokenTelemetryRecord.id) > 2
    ).order_by(
        desc("avg_inflation")
    ).limit(limit).all()

    return [
        {
            "signature": row.workload_signature,
            "avg_inflation_ratio": round(row.avg_inflation, 2),
            "request_count": row.count,
            "category": row.category or "unknown"
        }
        for row in results
    ]


def get_overall_spend_summary(db: Session) -> dict:
    """Get overall cost and token summary."""
    result = db.query(
        func.sum(TokenTelemetryRecord.estimated_cost).label("total_cost"),
        func.sum(TokenTelemetryRecord.prompt_tokens).label("prompt_tokens"),
        func.sum(TokenTelemetryRecord.completion_tokens).label("completion_tokens"),
        func.count(TokenTelemetryRecord.id).label("request_count")
    ).first()
    
    total_cost = result.total_cost or 0.0
    # Very rough 30 day estimate based on current db state (assuming this is all recent)
    # For a real system we'd look at daily averages over the last N days.
    monthly_est = total_cost * 30.0 
    
    return {
        "total_spend_usd": round(total_cost, 4),
        "estimated_monthly_usd": round(monthly_est, 2),
        "total_requests": result.request_count or 0,
        "prompt_tokens": result.prompt_tokens or 0,
        "completion_tokens": result.completion_tokens or 0,
        "total_tokens": (result.prompt_tokens or 0) + (result.completion_tokens or 0)
    }
