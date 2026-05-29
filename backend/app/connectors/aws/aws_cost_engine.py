"""AWS cost analytics engine — Phase 8D.

Pure-function cost normalization and analytics.
This module performs NO AWS API calls — it processes the structured
output from aws_client.get_cost_explorer_summary().
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("qorvexis.connectors.aws.cost_engine")


class AWSCostEngine:
    """Normalizes and analyzes AWS Cost Explorer data into intelligence summaries."""

    def compute_summary(self, ce_response: dict) -> dict:
        """Compute a structured cost intelligence summary from CE raw output.

        Args:
            ce_response: Output from AWSClient.get_cost_explorer_summary()

        Returns:
            Dict with monthly_spend, daily_spend, service_breakdown,
            top_services, trend analysis, and category splits.
        """
        daily_costs       = ce_response.get("daily_costs", [])
        monthly_total     = ce_response.get("monthly_total", 0.0)
        daily_spend       = ce_response.get("daily_spend", 0.0)
        service_breakdown = ce_response.get("service_breakdown", {})

        # Trend: compare last 7 days vs prior 7 days
        spend_trend = self._compute_trend(daily_costs)

        # Category splits
        ec2_spend        = self._extract_service(service_breakdown, ["Amazon EC2", "Amazon Elastic Compute Cloud"])
        networking_spend = self._extract_service(service_breakdown, ["AWS Data Transfer", "Amazon CloudFront"])
        storage_spend    = self._extract_service(service_breakdown, ["Amazon S3", "Amazon EBS", "Amazon Glacier"])
        other_spend      = max(0.0, round(monthly_total - ec2_spend - networking_spend - storage_spend, 4))

        # Top services by spend
        top_services = sorted(
            [{"service": k, "amount": v} for k, v in service_breakdown.items() if v > 0],
            key=lambda x: x["amount"],
            reverse=True,
        )[:10]

        return {
            "monthly_spend":      round(monthly_total, 2),
            "daily_spend":        round(daily_spend, 4),
            "daily_costs":        daily_costs[-7:],      # last 7 days for trend display
            "service_breakdown":  service_breakdown,
            "top_services":       top_services,
            "category_breakdown": {
                "ec2":        round(ec2_spend, 2),
                "networking": round(networking_spend, 2),
                "storage":    round(storage_spend, 2),
                "other":      round(other_spend, 2),
            },
            "spend_trend": spend_trend,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_service(self, breakdown: dict, keys: list[str]) -> float:
        """Sum matching service names from the breakdown dict."""
        total = 0.0
        for k, v in breakdown.items():
            if any(key.lower() in k.lower() for key in keys):
                total += v
        return round(total, 4)

    def _compute_trend(self, daily_costs: list[dict]) -> dict:
        """Compare last 7 days to prior 7 days to compute a spend trend."""
        if len(daily_costs) < 14:
            return {"direction": "stable", "change_pct": 0.0, "data_points": len(daily_costs)}

        recent_7  = sum(d["amount"] for d in daily_costs[-7:])
        prior_7   = sum(d["amount"] for d in daily_costs[-14:-7])

        if prior_7 == 0:
            return {"direction": "stable", "change_pct": 0.0, "data_points": len(daily_costs)}

        change_pct = round(((recent_7 - prior_7) / prior_7) * 100, 1)
        direction  = "increasing" if change_pct > 5 else ("decreasing" if change_pct < -5 else "stable")

        return {
            "direction":   direction,
            "change_pct":  change_pct,
            "recent_7d":   round(recent_7, 2),
            "prior_7d":    round(prior_7, 2),
            "data_points": len(daily_costs),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
aws_cost_engine = AWSCostEngine()
