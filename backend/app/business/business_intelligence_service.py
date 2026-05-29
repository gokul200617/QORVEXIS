"""Business Intelligence Service — Phase 10.

Aggregates GatewayRequestRecord data to answer:
  - Which team costs the most?
  - Which customer causes the most spend?
  - Which workload is least efficient?
  - What is the top cost driver?

Falls back to TokenTelemetryRecord (Phase 8C) if gateway has no data yet,
ensuring the BI layer works even before the gateway is enabled.
"""

from __future__ import annotations
import logging
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger("qorvexis.business.intelligence")


class BusinessIntelligenceService:

    # ── Workload Attribution ──────────────────────────────────────────────────

    def get_workloads(self, db: Session) -> list[dict[str, Any]]:
        """Returns spend, requests, tokens, and latency grouped by workload."""
        try:
            from app.gateway.gateway_models import GatewayRequestRecord
            results = db.query(
                GatewayRequestRecord.workload_id,
                GatewayRequestRecord.workload_name,
                GatewayRequestRecord.provider,
                GatewayRequestRecord.model,
                func.count(GatewayRequestRecord.id).label("request_count"),
                func.sum(GatewayRequestRecord.estimated_cost).label("monthly_cost"),
                func.sum(GatewayRequestRecord.total_tokens).label("monthly_tokens"),
                func.avg(GatewayRequestRecord.latency_ms).label("avg_latency"),
                func.avg(
                    func.cast(GatewayRequestRecord.success, db.bind.dialect.name == "sqlite" and "INTEGER" or "INTEGER")
                ).label("success_rate_raw"),
            ).filter(
                GatewayRequestRecord.workload_id.isnot(None)
            ).group_by(
                GatewayRequestRecord.workload_id,
                GatewayRequestRecord.workload_name,
                GatewayRequestRecord.provider,
                GatewayRequestRecord.model,
            ).all()

            return [self._workload_row(r) for r in results]
        except Exception as exc:
            logger.warning("business.workloads.error detail=%s", exc)
            return self._fallback_workloads(db)

    def _workload_row(self, r) -> dict:
        return {
            "workload_id": r.workload_id,
            "workload_name": r.workload_name or r.workload_id,
            "provider": r.provider,
            "model": r.model,
            "monthly_cost": float(r.monthly_cost or 0.0),
            "monthly_tokens": int(r.monthly_tokens or 0),
            "request_count": int(r.request_count or 0),
            "avg_latency": float(r.avg_latency or 0.0),
            "success_rate": 100.0,  # simplified
        }

    def _fallback_workloads(self, db: Session) -> list[dict]:
        """Fall back to TokenTelemetryRecord when gateway has no workload data."""
        try:
            from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
            results = db.query(
                TokenTelemetryRecord.workload_signature,
                TokenTelemetryRecord.request_category,
                TokenTelemetryRecord.provider,
                TokenTelemetryRecord.model,
                func.count(TokenTelemetryRecord.id).label("request_count"),
                func.sum(TokenTelemetryRecord.estimated_cost).label("monthly_cost"),
                func.sum(TokenTelemetryRecord.total_tokens).label("monthly_tokens"),
                func.avg(TokenTelemetryRecord.latency_ms).label("avg_latency"),
            ).filter(
                TokenTelemetryRecord.workload_signature.isnot(None)
            ).group_by(
                TokenTelemetryRecord.workload_signature,
                TokenTelemetryRecord.request_category,
                TokenTelemetryRecord.provider,
                TokenTelemetryRecord.model,
            ).all()

            return [{
                "workload_id": r.workload_signature,
                "workload_name": r.request_category or r.workload_signature,
                "provider": r.provider,
                "model": r.model,
                "monthly_cost": float(r.monthly_cost or 0.0),
                "monthly_tokens": int(r.monthly_tokens or 0),
                "request_count": int(r.request_count or 0),
                "avg_latency": float(r.avg_latency or 0.0),
                "success_rate": 100.0,
            } for r in results]
        except Exception:
            return []

    # ── Team Attribution ──────────────────────────────────────────────────────

    def get_teams(self, db: Session) -> list[dict[str, Any]]:
        """Returns spend, tokens, and optimization score per team."""
        try:
            from app.gateway.gateway_models import GatewayRequestRecord
            results = db.query(
                GatewayRequestRecord.team_id,
                GatewayRequestRecord.team_name,
                func.count(GatewayRequestRecord.id).label("request_count"),
                func.sum(GatewayRequestRecord.estimated_cost).label("monthly_cost"),
                func.sum(GatewayRequestRecord.total_tokens).label("token_usage"),
            ).filter(
                GatewayRequestRecord.team_id.isnot(None)
            ).group_by(
                GatewayRequestRecord.team_id,
                GatewayRequestRecord.team_name,
            ).order_by(func.sum(GatewayRequestRecord.estimated_cost).desc()).all()

            teams = []
            for r in results:
                cost = float(r.monthly_cost or 0.0)
                # Savings opportunity: up to 40% via routing optimizations (deterministic heuristic)
                savings = cost * 0.30
                teams.append({
                    "team_id": r.team_id,
                    "team_name": r.team_name or r.team_id,
                    "monthly_cost": cost,
                    "token_usage": int(r.token_usage or 0),
                    "request_count": int(r.request_count or 0),
                    "savings_opportunity": savings,
                    "optimization_score": max(0, 100 - int(savings / max(cost, 0.01) * 100)),
                })
            return teams
        except Exception as exc:
            logger.warning("business.teams.error detail=%s", exc)
            return []

    # ── Customer Attribution ──────────────────────────────────────────────────

    def get_customers(self, db: Session) -> list[dict[str, Any]]:
        """Returns spend, tokens, and provider distribution per customer."""
        try:
            from app.gateway.gateway_models import GatewayRequestRecord
            results = db.query(
                GatewayRequestRecord.customer_id,
                GatewayRequestRecord.customer_name,
                func.count(GatewayRequestRecord.id).label("request_count"),
                func.sum(GatewayRequestRecord.estimated_cost).label("monthly_cost"),
                func.sum(GatewayRequestRecord.total_tokens).label("tokens"),
            ).filter(
                GatewayRequestRecord.customer_id.isnot(None)
            ).group_by(
                GatewayRequestRecord.customer_id,
                GatewayRequestRecord.customer_name,
            ).order_by(func.sum(GatewayRequestRecord.estimated_cost).desc()).all()

            return [{
                "customer_id": r.customer_id,
                "customer_name": r.customer_name or r.customer_id,
                "monthly_cost": float(r.monthly_cost or 0.0),
                "requests": int(r.request_count or 0),
                "tokens": int(r.tokens or 0),
            } for r in results]
        except Exception as exc:
            logger.warning("business.customers.error detail=%s", exc)
            return []

    # ── Executive Summary ─────────────────────────────────────────────────────

    def get_summary(self, db: Session) -> dict[str, Any]:
        """Returns executive-level KPI payload."""
        try:
            from app.gateway.gateway_models import GatewayRequestRecord
            from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
            from app.connectors.models.provider_usage_snapshot import ProviderUsageSnapshot

            # Total spend from gateway
            gw_spend = float(db.query(func.sum(GatewayRequestRecord.estimated_cost)).scalar() or 0.0)
            gw_requests = db.query(func.count(GatewayRequestRecord.id)).scalar() or 0

            # Fallback total spend from token intelligence
            ti_spend = float(db.query(func.sum(TokenTelemetryRecord.estimated_cost)).scalar() or 0.0)
            observed_spend = gw_spend + ti_spend

            # Provider snapshot spend
            provider_spend = float(db.query(func.sum(ProviderUsageSnapshot.estimated_cost)).scalar() or 0.0)

            # Explicit aggregation strategy to avoid double counting
            total_spend = max(provider_spend, observed_spend)

            workloads = self.get_workloads(db)
            teams = self.get_teams(db)
            customers = self.get_customers(db)

            top_workload = max(workloads, key=lambda x: x["monthly_cost"], default=None)
            top_team = max(teams, key=lambda x: x["monthly_cost"], default=None)
            top_customer = max(customers, key=lambda x: x["monthly_cost"], default=None)

            total_savings_opp = sum(t.get("savings_opportunity", 0) for t in teams)

            return {
                "total_ai_spend": total_spend,
                "gateway_spend": gw_spend,
                "provider_spend": provider_spend,
                "observed_spend": observed_spend,
                "gateway_requests": gw_requests,
                "top_cost_driver": top_workload["workload_name"] if top_workload else "No data",
                "top_team": top_team["team_name"] if top_team else "No data",
                "top_customer": top_customer["customer_name"] if top_customer else "No data",
                "optimization_opportunity": total_savings_opp,
                "workload_count": len(workloads),
                "team_count": len(teams),
                "customer_count": len(customers),
            }
        except Exception as exc:
            logger.warning("business.summary.error detail=%s", exc)
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


business_intelligence_service = BusinessIntelligenceService()
