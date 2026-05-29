"""Unified Provider Summary Service.

Prepares the GET /providers/summary payload by stitching together
intelligence, distributions, and optimization metrics.
"""

from sqlalchemy.orm import Session
from app.connectors.services.provider_intelligence_service import provider_intelligence_service
from app.connectors.services.provider_optimization_engine import provider_optimization_engine
from app.connectors.registry.connector_registry import connector_registry
from app.connectors.base.connector_types import ConnectorType


class ProviderSummaryService:
    def get_summary(self, db: Session) -> dict:
        """Returns the high-level KPI dashboard payload for AI providers."""
        dist = provider_intelligence_service.get_provider_distribution(db)
        recs = provider_optimization_engine.generate_recommendations(db)
        workloads = provider_optimization_engine.get_workload_attributions(db)

        total_ai_spend = sum(stats["spend"] for stats in dist.values())
        active_providers = len([c for c in connector_registry.list_connectors(ConnectorType.AI_PROVIDER) if c.status.value == "connected"])
        
        top_provider = None
        max_reqs = -1
        for prov, stats in dist.items():
            if stats["requests"] > max_reqs:
                max_reqs = stats["requests"]
                top_provider = prov

        top_model = None
        max_model_reqs = -1
        for w in workloads:
            if w["requests"] > max_model_reqs:
                max_model_reqs = w["requests"]
                top_model = w["model"]

        estimated_savings = sum(r["estimated_savings"] for r in recs)
        
        # Simple optimization score: 100 - (waste penalties)
        waste_penalty = min(len(recs) * 5, 50)  # up to 50 points lost for un-optimized workloads
        optimization_score = 100 - waste_penalty

        most_expensive_workload = None
        if workloads:
            most_expensive_workload = workloads[0]["category"] # Since they are sorted by spend descending

        return {
            "total_ai_spend": total_ai_spend,
            "active_providers": active_providers,
            "top_provider": top_provider or "None",
            "top_model": top_model or "None",
            "estimated_savings": estimated_savings,
            "optimization_score": optimization_score,
            "most_expensive_workload": most_expensive_workload or "None",
            "provider_distribution": dist,
        }


provider_summary_service = ProviderSummaryService()
