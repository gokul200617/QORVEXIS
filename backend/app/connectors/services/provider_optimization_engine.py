"""Provider Optimization Engine.

Applies deterministic rules to DB workload signatures to identify provider routing,
cost reduction, and caching opportunities. No generic AI advice allowed.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
from typing import Any


class ProviderOptimizationEngine:
    def get_workload_attributions(self, db: Session) -> list[dict[str, Any]]:
        """Groups token telemetry by workload_signature to find spend vectors."""
        # Query total spend, requests, tokens, average latency per workload signature
        results = db.query(
            TokenTelemetryRecord.workload_signature,
            TokenTelemetryRecord.request_category,
            TokenTelemetryRecord.provider,
            TokenTelemetryRecord.model,
            func.count(TokenTelemetryRecord.id).label("requests"),
            func.sum(TokenTelemetryRecord.estimated_cost).label("spend"),
            func.avg(TokenTelemetryRecord.latency_ms).label("latency"),
            func.avg(TokenTelemetryRecord.total_tokens).label("avg_tokens")
        ).filter(TokenTelemetryRecord.workload_signature.isnot(None))\
         .group_by(
             TokenTelemetryRecord.workload_signature,
             TokenTelemetryRecord.request_category,
             TokenTelemetryRecord.provider,
             TokenTelemetryRecord.model
         ).all()

        workloads = []
        for row in results:
            workloads.append({
                "workload_signature": row.workload_signature,
                "category": row.request_category or "Unknown",
                "provider": row.provider,
                "model": row.model,
                "requests": row.requests,
                "spend": float(row.spend or 0.0),
                "avg_latency": float(row.latency or 0.0),
                "avg_tokens": int(row.avg_tokens or 0)
            })
        
        # Sort by spend descending
        workloads.sort(key=lambda x: x["spend"], reverse=True)
        return workloads

    def generate_recommendations(self, db: Session) -> list[dict[str, Any]]:
        """Analyzes workloads and applies deterministic routing rules."""
        workloads = self.get_workload_attributions(db)
        recommendations = []

        for w in workloads:
            # Rule 1: GPT-4o / GPT-4 for low-token workloads
            if ("gpt-4" in w["model"].lower() and "mini" not in w["model"].lower()) and w["avg_tokens"] < 1500:
                # Roughly 70% cheaper
                savings = w["spend"] * 0.70
                if savings > 0.1:
                    recommendations.append({
                        "type": "model_downgrade",
                        "workload": w["category"],
                        "current_provider": w["provider"],
                        "current_model": w["model"],
                        "rule": "Low-token workload running on expensive flagship model",
                        "recommendation": "Move to GPT-4o-mini",
                        "estimated_savings": savings
                    })

            # Rule 2: High volume requests on an expensive provider (OpenAI/Gemini) -> Route to Groq
            if w["requests"] > 1000 and w["provider"] != "groq" and w["avg_tokens"] < 3000:
                savings = w["spend"] * 0.85
                if savings > 1.0:
                    recommendations.append({
                        "type": "provider_migration",
                        "workload": w["category"],
                        "current_provider": w["provider"],
                        "current_model": w["model"],
                        "rule": "High-volume workload on slower/expensive provider",
                        "recommendation": "Route to Groq (Llama 3)",
                        "estimated_savings": savings
                    })

            # Rule 3: High identical repetitions (cacheable)
            if w["requests"] > 500 and w["avg_tokens"] > 500:
                savings = w["spend"] * 0.90 # 90% savings assuming high hit rate
                if savings > 0.5:
                    recommendations.append({
                        "type": "caching_opportunity",
                        "workload": w["category"],
                        "current_provider": w["provider"],
                        "current_model": w["model"],
                        "rule": "Repeated high-token workload",
                        "recommendation": "Enable Qorvexis semantic caching",
                        "estimated_savings": savings
                    })

        return recommendations


provider_optimization_engine = ProviderOptimizationEngine()
