"""AWS Connector Summary Service — Phase 8D.

Single-purpose service that aggregates all AWS intelligence into one
dashboard-ready payload, reducing frontend complexity and API round-trips.

The frontend should call GET /connectors/aws/summary instead of
independently calling infrastructure, costs, and recommendations endpoints.
"""

from __future__ import annotations

import logging

from app.connectors.aws.aws_usage_service import aws_usage_service

logger = logging.getLogger("qorvexis.connectors.aws.summary_service")


class AWSConnectorSummaryService:
    """Builds and returns the aggregated AWS dashboard summary."""

    def get_summary(self) -> dict:
        """Return the single aggregated dashboard payload.

        Structure:
          monthly_spend              — float (USD)
          daily_spend                — float (USD)
          active_instances           — int
          total_instances            — int
          underutilized_instances    — int
          estimated_savings          — float (monthly USD)
          infrastructure_health_score — float (0-100)
          optimization_score         — float (0-100)
          waste_score                — float (0-100)
          connector_status           — str (idle | syncing | completed | degraded | failed)
          last_sync                  — ISO timestamp or null
          sync_state                 — sync lifecycle detail
          account_metadata           — account_id, alias, region, etc.
          recommendation_count       — int
          top_recommendations        — list of top 3 recommendations
          available                  — bool
        """
        try:
            summary = aws_usage_service.get_dashboard_summary()
            logger.debug(
                "aws.summary_service.get_summary available=%s instances=%s",
                summary.get("available"),
                summary.get("active_instances"),
            )
            return summary
        except Exception as exc:
            logger.error("aws.summary_service.get_summary.error detail=%s", exc)
            return {
                "monthly_spend":               0.0,
                "daily_spend":                 0.0,
                "active_instances":            0,
                "total_instances":             0,
                "underutilized_instances":     0,
                "estimated_savings":           0.0,
                "infrastructure_health_score": 0.0,
                "optimization_score":          0.0,
                "waste_score":                 0.0,
                "connector_status":            "error",
                "last_sync":                   None,
                "sync_state":                  {},
                "account_metadata":            {},
                "recommendation_count":        0,
                "top_recommendations":         [],
                "available":                   False,
                "reason":                      f"Summary service error: {exc}",
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
aws_connector_summary_service = AWSConnectorSummaryService()
