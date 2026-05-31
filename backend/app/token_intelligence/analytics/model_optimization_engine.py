"""Model Optimization Engine.

Evaluates historical telemetry to detect workloads that are over-provisioned 
(e.g., simple workloads using expensive models) and generates 
deterministic recommendations.
"""

import uuid
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
from app.token_intelligence.pricing.pricing_engine import estimate_monthly_cost, estimate_cost


def generate_recommendations(db: Session, org_id: str | None = None) -> List[Dict[str, Any]]:
    """Analyze recent telemetry to generate cost optimization recommendations."""
    recommendations = []
    
    # 1. Check for expensive model overuse on low-token workloads
    low_token_gpt4o = db.query(
        TokenTelemetryRecord.request_category,
        func.count(TokenTelemetryRecord.id).label("count"),
        func.avg(TokenTelemetryRecord.estimated_cost).label("avg_cost"),
        func.avg(TokenTelemetryRecord.prompt_tokens).label("avg_prompt"),
        func.avg(TokenTelemetryRecord.completion_tokens).label("avg_completion")
    ).filter(
        TokenTelemetryRecord.model.ilike("%gpt-4o%"),
        TokenTelemetryRecord.model.notilike("%mini%"),
        TokenTelemetryRecord.total_tokens < 200
    ).group_by(TokenTelemetryRecord.request_category).all()
    
    for row in low_token_gpt4o:
        category, count, avg_cost, avg_prompt, avg_comp = row
        if count > 10:  # Threshold to avoid noise
            # Estimate what it would have cost on gpt-4o-mini
            avg_mini_cost = estimate_cost("openai", "gpt-4o-mini", avg_prompt, avg_comp)
            savings_per_req = avg_cost - avg_mini_cost
            if savings_per_req > 0:
                est_monthly_savings = estimate_monthly_cost(savings_per_req * count) # Rough estimate based on recent volume
                cat_str = category or "general"
                recommendations.append({
                    "rule_id": "downgrade_gpt4o",
                    "severity": "info",
                    "title": f"Downgrade opportunity for {cat_str} workloads",
                    "detail": f"{count} low-token {cat_str} workloads currently use GPT-4o. Estimated savings opportunity by routing to GPT-4o-mini.",
                    "estimated_monthly_waste_usd": est_monthly_savings,
                    "estimated_savings_usd": est_monthly_savings
                })

    # 2. Check for high completion inflation in support/chat
    high_inflation = db.query(
        func.avg(TokenTelemetryRecord.completion_inflation_ratio).label("avg_inflation"),
        func.count(TokenTelemetryRecord.id).label("count")
    ).filter(
        TokenTelemetryRecord.request_category.in_(["support", "chat"]),
        TokenTelemetryRecord.completion_inflation_ratio > 3.0
    ).first()
    
    if high_inflation and high_inflation.count and high_inflation.count > 10:
        recommendations.append({
            "rule_id": "high_inflation_support",
            "severity": "warning",
            "title": "High Completion Inflation Detected",
            "detail": f"Average completion inflation ratio exceeds efficient threshold ({high_inflation.avg_inflation:.1f}x) for support/chat workloads.",
            "estimated_monthly_waste_usd": 0.0, # Hard to estimate without knowing prompt intent
            "estimated_savings_usd": 0.0
        })

    return recommendations
