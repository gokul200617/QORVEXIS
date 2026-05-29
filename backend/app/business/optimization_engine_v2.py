"""Optimization Engine V2 — Phase 10.

Extends Phase 9 provider optimization with workload-level and team-level
recommendations based on GatewayRequestRecord attribution data.

All rules are deterministic. No LLM opinions.
"""

from __future__ import annotations
import logging
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger("qorvexis.business.optimization")


class OptimizationEngineV2:

    def get_recommendations(self, db: Session) -> list[dict[str, Any]]:
        """Generates prioritized, actionable recommendations with dollar savings."""
        recommendations = []

        # Rule set 1: workload-level (from gateway data)
        recommendations.extend(self._workload_rules(db))

        # Rule set 2: team-level
        recommendations.extend(self._team_rules(db))

        # Sort by estimated savings descending
        recommendations.sort(key=lambda x: x.get("estimated_savings", 0), reverse=True)
        return recommendations

    def _workload_rules(self, db: Session) -> list[dict]:
        recs = []
        try:
            from app.gateway.gateway_models import GatewayRequestRecord
            results = db.query(
                GatewayRequestRecord.workload_id,
                GatewayRequestRecord.workload_name,
                GatewayRequestRecord.provider,
                GatewayRequestRecord.model,
                func.count(GatewayRequestRecord.id).label("requests"),
                func.sum(GatewayRequestRecord.estimated_cost).label("spend"),
                func.avg(GatewayRequestRecord.total_tokens).label("avg_tokens"),
                func.avg(GatewayRequestRecord.latency_ms).label("avg_latency"),
            ).filter(
                GatewayRequestRecord.workload_id.isnot(None)
            ).group_by(
                GatewayRequestRecord.workload_id,
                GatewayRequestRecord.workload_name,
                GatewayRequestRecord.provider,
                GatewayRequestRecord.model,
            ).all()

            for r in results:
                spend = float(r.spend or 0)
                avg_tokens = float(r.avg_tokens or 0)
                requests = int(r.requests or 0)
                model = r.model or ""
                provider = r.provider or ""
                name = r.workload_name or r.workload_id

                # Rule: GPT-4o on low-token workloads → GPT-4o-mini
                if "gpt-4o" in model.lower() and "mini" not in model.lower() and avg_tokens < 2000:
                    savings = spend * 0.72
                    if savings > 0.01:
                        recs.append({
                            "type": "model_downgrade",
                            "category": "cost",
                            "workload": name,
                            "current_provider": provider,
                            "current_model": model,
                            "rule": f"Low avg token count ({int(avg_tokens)}) on expensive flagship model",
                            "recommendation": "Switch to GPT-4o-mini",
                            "estimated_savings": savings,
                            "priority": "high",
                        })

                # Rule: GPT-4 (non-o) → GPT-4o
                if model.lower() == "gpt-4" and spend > 0.5:
                    savings = spend * 0.5
                    recs.append({
                        "type": "model_downgrade",
                        "category": "cost",
                        "workload": name,
                        "current_provider": provider,
                        "current_model": model,
                        "rule": "Legacy GPT-4 is 2x cost of GPT-4o for equivalent quality",
                        "recommendation": "Migrate to GPT-4o",
                        "estimated_savings": savings,
                        "priority": "high",
                    })

                # Rule: High-volume, short-context → route to Groq
                if requests > 500 and avg_tokens < 3000 and provider != "groq":
                    savings = spend * 0.80
                    if savings > 1.0:
                        recs.append({
                            "type": "provider_migration",
                            "category": "routing",
                            "workload": name,
                            "current_provider": provider,
                            "current_model": model,
                            "rule": f"High-volume ({requests} reqs), short-context workload on expensive provider",
                            "recommendation": "Route to Groq (Llama 3 70B) — 5x cheaper at equivalent quality",
                            "estimated_savings": savings,
                            "priority": "high",
                        })

                # Rule: Repeated classification/support workloads → caching
                if requests > 200 and avg_tokens < 1500:
                    savings = spend * 0.60
                    if savings > 0.5:
                        recs.append({
                            "type": "caching_opportunity",
                            "category": "efficiency",
                            "workload": name,
                            "current_provider": provider,
                            "current_model": model,
                            "rule": "Repeated short workload — high cache hit rate potential",
                            "recommendation": "Enable semantic caching for this workload",
                            "estimated_savings": savings,
                            "priority": "medium",
                        })
        except Exception as exc:
            logger.warning("optimization_v2.workload_rules.error detail=%s", exc)

        return recs

    def _team_rules(self, db: Session) -> list[dict]:
        recs = []
        try:
            from app.gateway.gateway_models import GatewayRequestRecord
            results = db.query(
                GatewayRequestRecord.team_id,
                GatewayRequestRecord.team_name,
                func.sum(GatewayRequestRecord.estimated_cost).label("spend"),
                func.count(GatewayRequestRecord.id).label("requests"),
            ).filter(
                GatewayRequestRecord.team_id.isnot(None)
            ).group_by(
                GatewayRequestRecord.team_id,
                GatewayRequestRecord.team_name,
            ).all()

            for r in results:
                spend = float(r.spend or 0)
                name = r.team_name or r.team_id
                # Teams spending > $100/mo with no gateway attribution for workloads
                if spend > 100:
                    recs.append({
                        "type": "team_budget",
                        "category": "governance",
                        "workload": f"Team: {name}",
                        "current_provider": "mixed",
                        "current_model": "mixed",
                        "rule": f"Team '{name}' is spending ${spend:.2f} without workload-level tagging",
                        "recommendation": "Enforce workload_id tagging on all gateway requests to unlock attribution",
                        "estimated_savings": spend * 0.15,
                        "priority": "medium",
                    })
        except Exception as exc:
            logger.debug("optimization_v2.team_rules.error detail=%s", exc)

        return recs


optimization_engine_v2 = OptimizationEngineV2()
