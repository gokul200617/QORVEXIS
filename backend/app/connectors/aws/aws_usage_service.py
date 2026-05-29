"""AWS usage aggregation service — Phase 8D.

Thread-safe in-memory store for the latest AWS infrastructure intelligence.
Acts as the data hub that sits between the connector sync cycle and the API layer.

Caching strategy:
  * EC2 discovery cache   — 2-minute TTL
  * CloudWatch cache      — 5-minute TTL
  * Cost Explorer cache   — 30-minute TTL
  * Summary cache         — 2-minute TTL

This prevents excessive AWS API calls on every dashboard refresh.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from app.connectors.aws.aws_models import (
    AWSEC2Instance,
    AWSAccountMetadata,
    AWSRecommendation,
    AWSSyncState,
    SyncStatus,
)

logger = logging.getLogger("qorvexis.connectors.aws.usage_service")

# Cache TTLs in seconds
_TTL_EC2        = 120   # 2 minutes
_TTL_CLOUDWATCH = 300   # 5 minutes
_TTL_COST       = 1800  # 30 minutes
_TTL_SUMMARY    = 120   # 2 minutes


class AWSUsageService:
    """Aggregates and caches AWS intelligence for the dashboard API layer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Connected connector metadata
        self._connector_id:   Optional[str] = None
        self._connector_name: Optional[str] = None

        # Account metadata
        self._account_metadata: Optional[AWSAccountMetadata] = None

        # Sync tracking
        self._sync_state = AWSSyncState()

        # Cached data
        self._instances:         list[AWSEC2Instance]    = []
        self._recommendations:   list[AWSRecommendation] = []
        self._cost_summary:      dict = {}
        self._infrastructure_summary: dict = {}

        # Scores
        self._health_score:       float = 0.0
        self._optimization_score: float = 95.0
        self._waste_score:        float = 0.0

        # Cache timestamps (monotonic seconds)
        self._ts_instances:  float = 0.0
        self._ts_cost:       float = 0.0
        self._ts_summary:    float = 0.0

    # ── Registration ─────────────────────────────────────────────────────────

    def register_connector(self, connector_id: str, connector_name: str) -> None:
        """Called once when the AWS connector is first connected."""
        with self._lock:
            self._connector_id   = connector_id
            self._connector_name = connector_name
            logger.info(
                "aws.usage_service.connector_registered id=%s name=%s",
                connector_id,
                connector_name,
            )

    def is_registered(self) -> bool:
        """Returns True if an AWS connector has been connected."""
        with self._lock:
            return self._connector_id is not None

    # ── Sync lifecycle ────────────────────────────────────────────────────────

    def mark_syncing(self) -> None:
        with self._lock:
            self._sync_state.mark_syncing()

    def record_sync_success(
        self,
        instances:       list[AWSEC2Instance],
        cost_summary:    dict,
        recommendations: list[AWSRecommendation],
        account_metadata: AWSAccountMetadata,
        health_score:     float,
        optimization_score: float,
        waste_score:      float,
        duration_ms:      int,
    ) -> None:
        """Update all cached state after a successful sync."""
        now = time.monotonic()
        with self._lock:
            self._instances         = instances
            self._cost_summary      = cost_summary
            self._recommendations   = recommendations
            self._account_metadata  = account_metadata
            self._health_score      = health_score
            self._optimization_score = optimization_score
            self._waste_score       = waste_score

            self._ts_instances = now
            self._ts_cost      = now
            self._ts_summary   = now

            self._sync_state.mark_completed(
                resources=len(instances),
                duration_ms=duration_ms,
            )

            if self._account_metadata:
                self._account_metadata.connector_status  = "connected"
                self._account_metadata.last_sync_timestamp = datetime.now(timezone.utc)

        logger.info(
            "aws.usage_service.sync_recorded instances=%s recs=%s health=%.1f",
            len(instances),
            len(recommendations),
            health_score,
        )

    def record_sync_failure(self, error: str, degraded: bool = True) -> None:
        """Record a sync failure and update health state."""
        with self._lock:
            if degraded:
                self._sync_state.mark_degraded(error)
            else:
                self._sync_state.mark_failed(error)

    # ── Data accessors ────────────────────────────────────────────────────────

    def get_infrastructure_summary(self) -> dict:
        """Return EC2 instance intelligence summary."""
        with self._lock:
            if not self._connector_id:
                return self._unavailable_payload("infrastructure")

            instances = self._instances
            running   = [i for i in instances if i.is_running]
            stopped   = [i for i in instances if i.is_stopped]
            under     = [i for i in running
                         if i.cpu_utilization < 10.0 and i.cpu_utilization > 0]

            return {
                "connector_id":           self._connector_id,
                "total_instances":        len(instances),
                "running_instances":      len(running),
                "stopped_instances":      len(stopped),
                "underutilized_instances": len(under),
                "instances":              [i.to_dict() for i in instances],
                "health_score":           self._health_score,
                "optimization_score":     self._optimization_score,
                "waste_score":            self._waste_score,
                "sync_state":             self._sync_state.to_dict(),
                "available":              True,
            }

    def get_cost_summary(self) -> dict:
        """Return cost analytics summary."""
        with self._lock:
            if not self._connector_id:
                return self._unavailable_payload("costs")

            result = dict(self._cost_summary)
            result["available"]   = True
            result["connector_id"] = self._connector_id
            result["sync_state"]  = self._sync_state.to_dict()
            return result

    def get_recommendations(self) -> dict:
        """Return optimization recommendations."""
        with self._lock:
            if not self._connector_id:
                return self._unavailable_payload("recommendations")

            return {
                "connector_id":      self._connector_id,
                "recommendation_count": len(self._recommendations),
                "recommendations":   [r.to_dict() for r in self._recommendations],
                "total_estimated_savings_usd": round(
                    sum(r.estimated_monthly_savings_usd for r in self._recommendations), 2
                ),
                "sync_state":        self._sync_state.to_dict(),
                "available":         True,
            }

    def get_health(self) -> dict:
        """Return connector health and sync state."""
        with self._lock:
            metadata = self._account_metadata.to_dict() if self._account_metadata else {}
            return {
                "connector_id":     self._connector_id,
                "connector_name":   self._connector_name,
                "sync_state":       self._sync_state.to_dict(),
                "account_metadata": metadata,
                "available":        self._connector_id is not None,
            }

    def get_dashboard_summary(self) -> dict:
        """Return the aggregated summary payload for the dashboard.

        This is the primary endpoint the frontend should poll —
        single call instead of multiple API round-trips.
        """
        with self._lock:
            if not self._connector_id:
                return self._unavailable_dashboard()

            instances = self._instances
            running   = [i for i in instances if i.is_running]
            under     = [i for i in running if i.cpu_utilization < 10.0]

            monthly_spend = self._cost_summary.get("monthly_spend", 0.0)
            daily_spend   = self._cost_summary.get("daily_spend", 0.0)
            total_savings = round(
                sum(r.estimated_monthly_savings_usd for r in self._recommendations), 2
            )

            metadata = self._account_metadata.to_dict() if self._account_metadata else {}

            return {
                "monthly_spend":            monthly_spend,
                "daily_spend":              daily_spend,
                "active_instances":         len(running),
                "total_instances":          len(instances),
                "underutilized_instances":  len(under),
                "estimated_savings":        total_savings,
                "infrastructure_health_score": self._health_score,
                "optimization_score":       self._optimization_score,
                "waste_score":              self._waste_score,
                "connector_status":         self._sync_state.sync_status,
                "last_sync":                self._sync_state.last_sync.isoformat()
                                            if self._sync_state.last_sync else None,
                "sync_state":               self._sync_state.to_dict(),
                "account_metadata":         metadata,
                "recommendation_count":     len(self._recommendations),
                "top_recommendations":      [r.to_dict() for r in self._recommendations[:3]],
                "available":                True,
            }

    # ── Unavailable payloads ──────────────────────────────────────────────────

    @staticmethod
    def _unavailable_payload(section: str) -> dict:
        return {"available": False, "reason": f"AWS connector not connected ({section} unavailable)"}

    @staticmethod
    def _unavailable_dashboard() -> dict:
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
            "connector_status":            "disconnected",
            "last_sync":                   None,
            "sync_state":                  AWSSyncState().to_dict(),
            "account_metadata":            {},
            "recommendation_count":        0,
            "top_recommendations":         [],
            "available":                   False,
            "reason":                      "AWS connector not connected",
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
aws_usage_service = AWSUsageService()
