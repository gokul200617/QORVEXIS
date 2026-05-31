"""Efficiency Engine.

Computes token efficiency score, duplicate workload percentage, 
and cache opportunity percentage.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
from app.token_intelligence.models.workload_signature import WorkloadSignatureRecord


def compute_efficiency_metrics(db: Session, org_id: str | None = None) -> dict:
    """Compute overall infrastructure token efficiency."""
    
    # Total requests
    total_requests = db.query(func.count(TokenTelemetryRecord.id)).scalar() or 0
    if total_requests == 0:
        return {
            "efficiency_score": 100.0,
            "duplicate_workload_pct": 0.0,
            "cache_opportunity_pct": 0.0,
            "avg_inflation_ratio": 0.0
        }
        
    # Duplicate workloads (requests that hit cache or were deduped natively)
    duplicates = db.query(func.count(TokenTelemetryRecord.id)).filter(
        (TokenTelemetryRecord.cache_hit == True) | (TokenTelemetryRecord.deduplicated == True)
    ).scalar() or 0
    
    # Cache opportunities (repeated workloads that were NOT cached/deduped)
    opportunities = db.query(func.count(TokenTelemetryRecord.id)).filter(
        TokenTelemetryRecord.cache_hit == False,
        TokenTelemetryRecord.deduplicated == False,
        TokenTelemetryRecord.workload_signature.in_(
            db.query(WorkloadSignatureRecord.signature).filter(WorkloadSignatureRecord.occurrence_count > 1)
        )
    ).scalar() or 0

    avg_inflation = db.query(func.avg(TokenTelemetryRecord.completion_inflation_ratio)).scalar() or 0.0

    duplicate_pct = (duplicates / total_requests) * 100.0
    opportunity_pct = (opportunities / total_requests) * 100.0
    
    # Heuristic efficiency score (100 is perfect, subtract penalties)
    # Penalty for missed cache opportunities and high inflation
    score = 100.0 - (opportunity_pct * 0.5)
    if avg_inflation > 2.0:
        score -= min(20.0, (avg_inflation - 2.0) * 5)
        
    return {
        "efficiency_score": max(0.0, round(score, 1)),
        "duplicate_workload_pct": round(duplicate_pct, 1),
        "cache_opportunity_pct": round(opportunity_pct, 1),
        "avg_inflation_ratio": round(avg_inflation, 2)
    }
