"""Provider Intelligence Service.

Aggregates true telemetry directly from TokenTelemetryRecord to generate
cross-provider analytics (cost, latency, usage).
"""

from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
from app.connectors.registry.connector_registry import connector_registry
from app.connectors.base.connector_types import ConnectorType


class ProviderIntelligenceService:
    def get_provider_distribution(self, db: Session, org_id: str | None = None) -> dict[str, dict[str, Any]]:
        """Returns requests, cost, and latency per provider."""
        results = db.query(
            TokenTelemetryRecord.provider,
            func.count(TokenTelemetryRecord.id).label("requests"),
            func.sum(TokenTelemetryRecord.estimated_cost).label("total_cost"),
            func.avg(TokenTelemetryRecord.latency_ms).label("avg_latency"),
            func.sum(TokenTelemetryRecord.total_tokens).label("total_tokens")
        ).group_by(TokenTelemetryRecord.provider).all()

        distribution = {}
        for row in results:
            distribution[row.provider] = {
                "requests": row.requests or 0,
                "spend": float(row.total_cost or 0.0),
                "average_latency_ms": float(row.avg_latency or 0.0),
                "total_tokens": int(row.total_tokens or 0)
            }
            
        # Ensure active providers without DB hits yet still show up
        for conn in connector_registry.list_connectors(ConnectorType.AI_PROVIDER):
            # provider name is often parsed from connector name or ID (e.g. "openai-...")
            prov_key = "openai" if "openai" in conn.connector_id else \
                       "groq" if "groq" in conn.connector_id else \
                       "gemini" if "gemini" in conn.connector_id else "unknown"
            if prov_key not in distribution:
                distribution[prov_key] = {
                    "requests": 0,
                    "spend": 0.0,
                    "average_latency_ms": 0.0,
                    "total_tokens": 0
                }

        return distribution

    def get_provider_comparison(self, db: Session, org_id: str | None = None) -> list[dict[str, Any]]:
        """Ranks providers across multiple dimensions."""
        dist = self.get_provider_distribution(db)
        if not dist:
            return []

        comparison = []
        for provider, stats in dist.items():
            reqs = stats["requests"]
            spend = stats["spend"]
            latency = stats["average_latency_ms"]
            tokens = stats["total_tokens"]
            
            # Efficiency heuristic based on cost per 1k tokens
            cost_per_1k = (spend / max(tokens, 1)) * 1000
            
            # Simulated reliability (this would ideally join with connector health)
            reliability = 100.0 if reqs > 0 else 0.0
            
            # Cost-to-performance: lower is better (cost * latency)
            cost_perf = cost_per_1k * latency if reqs > 0 else float("inf")

            comparison.append({
                "provider": provider,
                "spend": spend,
                "latency_ms": latency,
                "requests": reqs,
                "tokens": tokens,
                "cost_per_1k": cost_per_1k,
                "reliability_score": reliability,
                "cost_performance_score": cost_perf
            })

        # Rank logic can be applied later or sorted here.
        # Let's sort by request volume for default order
        comparison.sort(key=lambda x: x["requests"], reverse=True)
        return comparison


provider_intelligence_service = ProviderIntelligenceService()
